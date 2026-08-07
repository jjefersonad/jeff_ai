"""create_pdf_document(from_preview=…) (html-document-tools-task-pdf-from-preview-1)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

import src.tools.create_pdf_document_tool as pdf_tool
from src.models.html_document_input import HtmlDocumentInput


@pytest.fixture
def documents_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "documents"
    (root / "html").mkdir(parents=True)
    (root / "pdf").mkdir(parents=True)
    monkeypatch.setattr(pdf_tool, "_documents_base_dir", lambda: root)
    monkeypatch.setattr(
        pdf_tool,
        "_document_url_prefix",
        lambda: "http://localhost:3000/api/files",
    )
    return root


def _seed_preview(documents_root: Path, name: str, body: str = "<h1>Preview</h1>") -> str:
    path = documents_root / "html" / name
    path.write_text(body, encoding="utf-8")
    return name


async def test_from_preview_filename_generates_pdf(
    documents_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unit-1: from_preview autorizado → PDF + url /api/files/pdf/."""
    name = _seed_preview(documents_root, "20260807120000.html", "<p>Proposta</p>")
    monkeypatch.setattr(pdf_tool, "record_ownership", AsyncMock())
    monkeypatch.setattr(
        pdf_tool,
        "_current_user_owns_preview",
        AsyncMock(return_value=True),
    )

    out = await pdf_tool.create_pdf_document.coroutine(
        HtmlDocumentInput(from_preview=name)
    )

    assert "error" not in out
    assert out["metadata"]["kind"] == "pdf"
    assert "/api/files/pdf/" in out["url"]
    assert Path(out["path"]).is_file()
    assert Path(out["path"]).read_bytes()[:4] == b"%PDF"


async def test_from_preview_url_generates_pdf(
    documents_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """from_preview como URL /api/files/html/… também funciona."""
    name = _seed_preview(documents_root, "via-url.html")
    monkeypatch.setattr(pdf_tool, "record_ownership", AsyncMock())
    monkeypatch.setattr(
        pdf_tool,
        "_current_user_owns_preview",
        AsyncMock(return_value=True),
    )

    out = await pdf_tool.create_pdf_document.coroutine(
        HtmlDocumentInput(
            from_preview=f"http://localhost:3000/api/files/html/{name}"
        )
    )

    assert "error" not in out
    assert out["metadata"]["kind"] == "pdf"


async def test_from_preview_unauthorized_rejects_without_pdf(
    documents_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unit-2: from_preview de outro user → error, sem PDF novo."""
    name = _seed_preview(documents_root, "secret.html", "<p>secret</p>")
    record = AsyncMock()
    monkeypatch.setattr(pdf_tool, "record_ownership", record)
    monkeypatch.setattr(
        pdf_tool,
        "_current_user_owns_preview",
        AsyncMock(return_value=False),
    )

    before = list((documents_root / "pdf").glob("*.pdf"))
    out = await pdf_tool.create_pdf_document.coroutine(
        HtmlDocumentInput(from_preview=name)
    )

    assert "error" in out
    assert "path" not in out
    assert "url" not in out
    record.assert_not_called()
    after = list((documents_root / "pdf").glob("*.pdf"))
    assert after == before


async def test_from_preview_missing_file_rejects(
    documents_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unit-2: arquivo inexistente → error."""
    monkeypatch.setattr(pdf_tool, "record_ownership", AsyncMock())
    monkeypatch.setattr(
        pdf_tool,
        "_current_user_owns_preview",
        AsyncMock(return_value=True),
    )

    out = await pdf_tool.create_pdf_document.coroutine(
        HtmlDocumentInput(from_preview="does-not-exist.html")
    )

    assert "error" in out
    assert "path" not in out
    assert list((documents_root / "pdf").glob("*.pdf")) == []
