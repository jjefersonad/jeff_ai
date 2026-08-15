"""session-file-sandbox pathguard-1: authorize image embeds + read_document."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

import src.infrastructure.ownership.path_guard as path_guard
import src.infrastructure.ownership.store as ownership_store
import src.tools.create_docx_document_tool as docx_tool
import src.tools.read_document_tool as read_doc
from src.infrastructure.ownership.path_guard import PathNotAuthorizedError
from src.infrastructure.ownership.paths import user_kind_dir
from src.models.html_document_input import HtmlBlockInput, HtmlDocumentInput


_PNG_1X1 = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
    b"\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


class _FakeCursor:
    def __init__(self, *, owned_rows: list[tuple] | None = None) -> None:
        self.executed: list[tuple[str, tuple | None]] = []
        self._owned_rows = owned_rows or []
        self._fetch_idx = 0

    async def __aenter__(self) -> "_FakeCursor":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return None

    async def execute(self, query: str, params: tuple | None = None) -> None:
        self.executed.append((query, params))
        self._last_query = query
        self._last_params = params

    async def fetchone(self) -> tuple | None:
        q = getattr(self, "_last_query", "")
        if "chat_attachments" in q:
            return None
        if "generated_files" in q and self._owned_rows:
            # Return matching kind/filename for user
            params = self._last_params or ()
            for row in self._owned_rows:
                # row: (user_id, kind, filename) or (kind,)
                if len(row) == 3 and params and row[0] == params[0] and row[2] == params[1]:
                    return (row[1],)
                if len(row) == 1:
                    return row
            return None
        return None

    async def fetchall(self) -> list[tuple]:
        q = getattr(self, "_last_query", "")
        if "generated_files" in q and self._owned_rows:
            params = self._last_params or ()
            out = []
            for row in self._owned_rows:
                if len(row) == 3 and params and row[0] == params[0] and row[2] == params[1]:
                    out.append((row[1],))
            return out
        return []


class _FakeConnection:
    def __init__(self, cursor: _FakeCursor) -> None:
        self._cursor = cursor

    async def __aenter__(self) -> "_FakeConnection":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return None

    def cursor(self) -> _FakeCursor:
        return self._cursor


class _FakePool:
    def __init__(self, cursor: _FakeCursor) -> None:
        self._cursor = cursor

    def connection(self) -> _FakeConnection:
        return _FakeConnection(self._cursor)


def _patch_config(
    monkeypatch: pytest.MonkeyPatch,
    *,
    user_key: str,
    role: str = "user",
    thread_id: str = "thread-1",
) -> None:
    cfg = {
        "configurable": {
            "user_key": user_key,
            "role": role,
            "thread_id": thread_id,
        }
    }

    def _cfg() -> dict:
        return cfg

    monkeypatch.setattr(ownership_store, "get_config", _cfg)
    import src.infrastructure.ownership.tool_path_guard as tool_guard
    import src.tools.read_document_tool as read_mod

    monkeypatch.setattr(tool_guard, "get_config", _cfg)
    monkeypatch.setattr(read_mod, "get_config", _cfg)



# --- unit-1: create_docx refuses other user's image path --------------------


@pytest.mark.asyncio
async def test_create_docx_rejects_other_users_image_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """WHEN user embeds image owned by B THEN tool errors and writes no docx."""
    files_root = tmp_path / "files"
    monkeypatch.setenv("FILES_DIR", str(files_root))
    monkeypatch.setenv("WORKSPACE_DIR", str(tmp_path / "workspace"))
    _patch_config(monkeypatch, user_key="web:user-a", role="user")

    other = files_root / "user-b" / "images" / "secret.png"
    other.parent.mkdir(parents=True)
    other.write_bytes(_PNG_1X1)

    cursor = _FakeCursor()
    monkeypatch.setattr(path_guard, "get_pool", lambda: _FakePool(cursor))
    monkeypatch.setattr(ownership_store, "get_pool", lambda: _FakePool(cursor))
    monkeypatch.setattr(
        docx_tool,
        "_document_url_prefix",
        lambda: "http://localhost:3000/api/files",
    )
    monkeypatch.setattr(docx_tool, "record_ownership", AsyncMock())

    out = await docx_tool.create_docx_document.coroutine(
        HtmlDocumentInput(
            title="Doc",
            blocks=[
                HtmlBlockInput(type="paragraph", text="hi"),
                HtmlBlockInput(type="image", path=str(other)),
            ],
        )
    )

    assert "error" in out
    assert "path" not in out
    docs = files_root / "user-a" / "docs"
    assert not docs.exists() or list(docs.glob("*.docx")) == []


@pytest.mark.asyncio
async def test_path_guard_requires_kind_matching_subdir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Filename-only ownership under wrong subdir is denied (kind↔subdir)."""
    files_root = tmp_path / "files"
    monkeypatch.setenv("FILES_DIR", str(files_root))
    monkeypatch.setenv("WORKSPACE_DIR", str(tmp_path / "workspace"))

    # File lives under docs/ but DB says kind=image for same filename.
    path = files_root / "user-a" / "docs" / "same-name.png"
    path.parent.mkdir(parents=True)
    path.write_bytes(_PNG_1X1)

    cursor = _FakeCursor(
        owned_rows=[("user-a", "image", "same-name.png")],
    )
    monkeypatch.setattr(path_guard, "get_pool", lambda: _FakePool(cursor))

    with pytest.raises(PathNotAuthorizedError):
        await path_guard.authorize_session_path(
            path,
            user_id="user-a",
            role="user",
            thread_id="thread-1",
        )


# --- unit-2: read_document repo deny / owned attachment allow ---------------


@pytest.mark.asyncio
async def test_read_document_user_refuses_repo_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """WHEN role=user reads backend/src/.../agent.py THEN refuses."""
    monkeypatch.setenv("FILES_DIR", str(tmp_path / "files"))
    monkeypatch.setenv("WORKSPACE_DIR", str(tmp_path / "workspace"))
    _patch_config(monkeypatch, user_key="web:user-a", role="user")

    # Point REPO_ROOT at a fake tree with agent.py
    repo = tmp_path / "repo"
    agent = repo / "backend" / "src" / "agents" / "unified" / "agent.py"
    agent.parent.mkdir(parents=True)
    agent.write_text("SECRET_SOURCE = True\n", encoding="utf-8")
    monkeypatch.setattr(read_doc, "REPO_ROOT", repo)
    monkeypatch.setattr(read_doc, "_within_repo", lambda p: str(p).startswith(str(repo)))

    out = await read_doc.read_document.coroutine(
        str(agent),
    )
    assert "SECRET_SOURCE" not in out
    assert "negado" in out.lower() or "denied" in out.lower() or "error" in out.lower() or "recus" in out.lower() or "autoriz" in out.lower() or "fora" in out.lower() or "sandbox" in out.lower() or "Acesso" in out


@pytest.mark.asyncio
async def test_read_document_user_allows_owned_attachment_pdf(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """WHEN role=user reads owned PDF under files/<uid>/attachment/ THEN extracts text."""
    files_root = tmp_path / "files"
    monkeypatch.setenv("FILES_DIR", str(files_root))
    monkeypatch.setenv("WORKSPACE_DIR", str(tmp_path / "workspace"))
    _patch_config(monkeypatch, user_key="web:user-a", role="user")

    pdf_path = user_kind_dir("user-a", "reference") / "note.pdf"
    pdf_path.parent.mkdir(parents=True)
    # Minimal PDF with extractable text is heavy; stub MarkItDown instead.
    pdf_path.write_bytes(b"%PDF-1.4 owned")

    cursor = _FakeCursor()
    # chat_attachments hit

    class _AttCursor(_FakeCursor):
        async def fetchone(self) -> tuple | None:
            q = getattr(self, "_last_query", "")
            if "chat_attachments" in q:
                return (1,)
            return None

    att_cursor = _AttCursor()
    monkeypatch.setattr(path_guard, "get_pool", lambda: _FakePool(att_cursor))

    class _FakeMd:
        def convert(self, _path: str) -> object:
            return type("R", (), {"text_content": "Hello from owned PDF"})()

    monkeypatch.setattr(read_doc, "MarkItDown", _FakeMd)
    monkeypatch.setattr(read_doc, "REPO_ROOT", tmp_path / "repo")
    (tmp_path / "repo").mkdir(exist_ok=True)

    out = await read_doc.read_document.coroutine(str(pdf_path))
    assert "Hello from owned PDF" in out
