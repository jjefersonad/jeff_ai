"""create_docx_document via HTML pipeline (html-document-tools-task-docx-2)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

import src.tools.create_docx_document_tool as docx_tool
from src.domain.shared.errors import DomainError
from src.models.html_document_input import HtmlBlockInput, HtmlDocumentInput


@pytest.fixture
def documents_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "documents"
    monkeypatch.setattr(docx_tool, "require_user_docs_dir", AsyncMock(return_value=root))
    monkeypatch.setattr(
        docx_tool,
        "_document_url_prefix",
        lambda: "http://localhost:3000/api/files",
    )
    monkeypatch.setattr(docx_tool, "record_ownership", AsyncMock())
    return root


async def test_html_payload_returns_docx_url(documents_root: Path) -> None:
    """Unit-1: HTML válido → url /api/files/docx/ + kind=docx."""
    out = await docx_tool.create_docx_document.coroutine(
        HtmlDocumentInput(
            html="<h1>Relatório</h1><p>Corpo.</p>",
            title="Relatório",
        )
    )

    assert "error" not in out
    assert out["metadata"]["kind"] == "docx"
    assert "/api/files/docx/" in out["url"]
    path = Path(out["path"])
    assert path.is_file()
    assert path.read_bytes()[:2] == b"PK"


async def test_empty_input_rejects_without_file(documents_root: Path) -> None:
    """Unit-2a: entrada vazia → error, sem docx."""
    out = await docx_tool.create_docx_document.coroutine("Só título")

    assert "error" in out
    assert "path" not in out
    assert list(documents_root.glob("*.docx")) == []


async def test_converter_failure_leaves_no_partial(
    documents_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unit-2b: falha do converter → error, sem parcial."""
    from src.application.use_cases.render_html_document import RenderHtmlDocument

    class _Boom:
        async def convert(self, **_kwargs: object) -> bytes:
            raise RuntimeError("boom")

    monkeypatch.setattr(
        docx_tool,
        "_build_docx_render",
        lambda _output_dir=None: RenderHtmlDocument(
            converters={"docx": _Boom()},
            output_base_dir=documents_root,
            url_prefix="/api/files",
        ),
    )

    out = await docx_tool.create_docx_document.coroutine(
        HtmlDocumentInput(html="<p>x</p>", title="T")
    )

    assert "error" in out
    assert "path" not in out
    assert list(documents_root.glob("*.docx")) == []


async def test_blocks_still_work(documents_root: Path) -> None:
    out = await docx_tool.create_docx_document.coroutine(
        HtmlDocumentInput(
            title="Doc",
            blocks=[HtmlBlockInput(type="paragraph", text="olá")],
        )
    )
    assert "error" not in out
    assert out["metadata"]["kind"] == "docx"
