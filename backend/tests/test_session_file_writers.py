"""session-file-sandbox writers-1: docs/images/attachment under files/<uid>/."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

import src.infrastructure.attachments.store as attachment_store
import src.infrastructure.ownership.store as ownership_store
import src.tools.create_docx_document_tool as docx_tool
import src.tools.fetch_reference_image_tool as fetch_ref_tool
import src.tools.generate_image_tool as image_tool
from src.domain.imaging import ImageDesign
from src.infrastructure.media.reference_store import store_reference_bytes
from src.infrastructure.ownership.paths import user_kind_dir
from src.models.html_document_input import HtmlDocumentInput


_PNG_1X1 = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
    b"\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


class _FakeCursor:
    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple | None]] = []

    async def __aenter__(self) -> "_FakeCursor":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return None

    async def execute(self, query: str, params: tuple | None = None) -> None:
        self.executed.append((query, params))


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


def _patch_pool(module: object, monkeypatch: pytest.MonkeyPatch, cursor: _FakeCursor) -> None:
    monkeypatch.setattr(module, "get_pool", lambda: _FakePool(cursor))


def _patch_config(monkeypatch: pytest.MonkeyPatch, user_key: str | None) -> None:
    monkeypatch.setattr(
        ownership_store,
        "get_config",
        lambda: {"configurable": {"user_key": user_key}} if user_key else {"configurable": {}},
    )


# --- unit-1: DocumentOutput / create_docx → files/<uid>/docs/ ---------------


@pytest.mark.asyncio
async def test_create_docx_writes_under_user_docs_not_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """WHEN create_docx runs with user_id THEN file lands under files/<uid>/docs/."""
    files_root = tmp_path / "files"
    outputs = tmp_path / "outputs" / "documents"
    outputs.mkdir(parents=True)
    monkeypatch.setenv("FILES_DIR", str(files_root))
    monkeypatch.setenv("DOCUMENTS_DIR", str(outputs))
    _patch_config(monkeypatch, "web:user-a")
    cursor = _FakeCursor()
    _patch_pool(ownership_store, monkeypatch, cursor)
    monkeypatch.setattr(
        docx_tool,
        "_document_url_prefix",
        lambda: "http://localhost:3000/api/files",
    )

    out = await docx_tool.create_docx_document.coroutine(
        HtmlDocumentInput(html="<p>olá</p>", title="Doc")
    )

    assert "error" not in out, out
    path = Path(out["path"])
    assert path.is_file()
    assert path.parent == files_root / "user-a" / "docs"
    assert not any(outputs.rglob("*.docx"))
    inserts = [p for q, p in cursor.executed if q and "INSERT INTO generated_files" in q]
    assert inserts and inserts[0] == ("user-a", "docx", path.name)


# --- unit-2: image / attachment / reference → images/ or attachment/ --------


@pytest.mark.asyncio
async def test_create_image_writes_under_user_images(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """WHEN create_image_from_prompt runs THEN bytes land under files/<uid>/images/."""
    files_root = tmp_path / "files"
    legacy = tmp_path / "outputs" / "images"
    legacy.mkdir(parents=True)
    monkeypatch.setenv("FILES_DIR", str(files_root))
    _patch_config(monkeypatch, "web:user-a")
    cursor = _FakeCursor()
    _patch_pool(ownership_store, monkeypatch, cursor)

    class _FakeGen:
        def __init__(self, output_dir: Path | None = None) -> None:
            self._output_dir = output_dir

        async def generate(self, design: ImageDesign) -> object:
            from src.application.ports.image_gen import GeneratedImage

            out_dir = self._output_dir or (legacy)
            out_dir.mkdir(parents=True, exist_ok=True)
            path = out_dir / "20260101000000.png"
            path.write_bytes(_PNG_1X1)
            return GeneratedImage(
                path=str(path),
                url=f"/api/images/{path.name}",
                metadata={"prompt": design.prompt},
            )

    class _FakeStyles:
        async def get(self, *_a: object, **_k: object) -> None:
            return None

        async def save(self, *_a: object, **_k: object) -> None:
            return None

    from src.application.use_cases.plan_and_create_image import PlanAndCreateImage

    monkeypatch.setattr(
        image_tool,
        "build_plan_and_create_image",
        lambda output_dir=None: PlanAndCreateImage(
            image_gen=_FakeGen(output_dir),
            styles=_FakeStyles(),
        ),
    )

    out = await image_tool.create_image_from_prompt.coroutine("um gato")

    assert "error" not in out
    path = Path(out["path"])
    assert path.parent == files_root / "user-a" / "images"
    assert not any(legacy.rglob("*.png"))
    inserts = [p for q, p in cursor.executed if q and "INSERT INTO generated_files" in q]
    assert inserts and inserts[0][1] == "image"


@pytest.mark.asyncio
async def test_store_attachment_writes_under_user_attachment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """WHEN store_attachment runs THEN bytes land under files/<uid>/attachment/."""
    files_root = tmp_path / "files"
    monkeypatch.setenv("FILES_DIR", str(files_root))
    cursor = _FakeCursor()
    _patch_pool(attachment_store, monkeypatch, cursor)

    result = await attachment_store.store_attachment(
        thread_id="thread-1",
        user_id="user-a",
        data=b"%PDF-1.4 x",
        filename="report.pdf",
        content_type="application/pdf",
    )

    path = Path(result.storage_path)
    assert path.parent == files_root / "user-a" / "attachment"
    assert path.is_file()
    assert "thread-1" not in str(path.parent)


@pytest.mark.asyncio
async def test_fetch_reference_image_writes_attachment_and_records_ownership(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """WHEN fetch_reference_image runs THEN attachment/ + record_ownership(reference)."""
    files_root = tmp_path / "files"
    legacy = tmp_path / "outputs" / "references"
    legacy.mkdir(parents=True)
    monkeypatch.setenv("FILES_DIR", str(files_root))
    _patch_config(monkeypatch, "web:user-a")
    cursor = _FakeCursor()
    _patch_pool(ownership_store, monkeypatch, cursor)

    async def _fake_fetch(url: str) -> str:
        out_dir = user_kind_dir("user-a", "reference")
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / "ref.png"
        path.write_bytes(_PNG_1X1)
        return str(path)

    class _Port:
        def __init__(self, output_dir: Path | None = None) -> None:
            self._output_dir = output_dir

        async def fetch(self, url: str) -> str:
            return await _fake_fetch(url)

    monkeypatch.setattr(
        fetch_ref_tool,
        "build_reference_image_fetch",
        lambda output_dir=None: _Port(output_dir),
    )

    out = await fetch_ref_tool.fetch_reference_image.coroutine("https://example.com/a.png")

    assert "error" not in out
    path = Path(out["path"])
    assert path.parent == files_root / "user-a" / "attachment"
    assert not any(legacy.rglob("*"))
    inserts = [p for q, p in cursor.executed if q and "INSERT INTO generated_files" in q]
    assert inserts and inserts[0] == ("user-a", "reference", path.name)


@pytest.mark.asyncio
async def test_store_reference_bytes_target_is_user_attachment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """POST /api/references target dir is files/<uid>/attachment/ (via helper)."""
    files_root = tmp_path / "files"
    monkeypatch.setenv("FILES_DIR", str(files_root))
    out_dir = user_kind_dir("user-a", "reference")
    path = Path(store_reference_bytes(_PNG_1X1, output_dir=out_dir))
    assert path.parent == files_root / "user-a" / "attachment"


# --- unit-3: fail-closed without user_id — no legacy outputs write ----------


@pytest.mark.asyncio
async def test_record_ownership_fails_closed_without_user_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WHEN record_ownership has no user_id THEN it raises (no silent no-op)."""
    _patch_config(monkeypatch, None)
    cursor = _FakeCursor()
    _patch_pool(ownership_store, monkeypatch, cursor)

    with pytest.raises(Exception, match="user_id|identity|owner"):
        await ownership_store.record_ownership(kind="docx", filename="x.docx")

    assert cursor.executed == []


@pytest.mark.asyncio
async def test_create_docx_without_user_id_does_not_write_legacy_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """WHEN create_docx has no user_id THEN fail-closed and no outputs/documents file."""
    files_root = tmp_path / "files"
    outputs = tmp_path / "outputs" / "documents"
    outputs.mkdir(parents=True)
    monkeypatch.setenv("FILES_DIR", str(files_root))
    monkeypatch.setenv("DOCUMENTS_DIR", str(outputs))
    _patch_config(monkeypatch, None)
    monkeypatch.setattr(
        docx_tool,
        "_document_url_prefix",
        lambda: "http://localhost:3000/api/files",
    )

    out = await docx_tool.create_docx_document.coroutine(
        HtmlDocumentInput(html="<p>x</p>", title="T")
    )

    assert "error" in out
    assert "path" not in out
    assert not any(outputs.rglob("*.docx"))
    assert not files_root.exists() or not any(files_root.rglob("*.docx"))
