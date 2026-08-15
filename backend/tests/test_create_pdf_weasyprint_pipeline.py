"""create_pdf_document via HTML→WeasyPrint (html-document-tools-task-pdf-1)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

import src.tools.create_pdf_document_tool as pdf_tool
from src.models.html_document_input import HtmlDocumentInput


@pytest.fixture
def documents_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "documents"
    monkeypatch.setattr(pdf_tool, "require_user_docs_dir", AsyncMock(return_value=root))
    monkeypatch.setattr(
        pdf_tool,
        "_document_url_prefix",
        lambda: "http://localhost:3000/api/files",
    )
    return root


async def test_html_payload_writes_pdf_via_pipeline(
    documents_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unit-1: HTML válido → .pdf + url /api/files/pdf/ + kind=pdf."""
    record = AsyncMock()
    monkeypatch.setattr(pdf_tool, "record_ownership", record)

    out = await pdf_tool.create_pdf_document.coroutine(
        HtmlDocumentInput(
            html="<h1>Relatório</h1><p>Corpo do documento.</p>",
            title="Relatório",
        )
    )

    assert "error" not in out
    assert out["metadata"]["kind"] == "pdf"
    assert "/api/files/pdf/" in out["url"]
    path = Path(out["path"])
    assert path.is_file()
    assert path.parent == documents_root
    assert path.read_bytes()[:4] == b"%PDF"
    record.assert_awaited_once_with(kind="pdf", filename=path.name)


async def test_proposal_template_via_tool(
    documents_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unit-2: template proposal → sucesso kind=pdf."""
    monkeypatch.setattr(pdf_tool, "record_ownership", AsyncMock())

    out = await pdf_tool.create_pdf_document.coroutine(
        HtmlDocumentInput(
            template="proposal",
            data={
                "client_name": "Acme",
                "project_title": "Portal",
                "summary": "MVP",
                "investment": "R$ 10.000",
            },
            title="Proposta Acme",
        )
    )

    assert "error" not in out
    assert out["metadata"]["kind"] == "pdf"
    assert "/api/files/pdf/" in out["url"]
    assert Path(out["path"]).is_file()


async def test_ownership_failure_is_fail_closed(
    documents_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unit-3: falha de stamp → error, sem sucesso com url."""
    monkeypatch.setattr(
        pdf_tool,
        "record_ownership",
        AsyncMock(side_effect=RuntimeError("db down")),
    )

    out = await pdf_tool.create_pdf_document.coroutine(
        HtmlDocumentInput(html="<p>ok</p>", title="T")
    )

    assert "error" in out
    assert "ownership" in out["error"].lower() or "db down" in out["error"].lower()
    assert "path" not in out
    assert "url" not in out


async def test_invalid_plain_string_does_not_write_pdf(
    documents_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Entrada inválida → error e nenhum PDF."""
    monkeypatch.setattr(pdf_tool, "record_ownership", AsyncMock())

    out = await pdf_tool.create_pdf_document.coroutine("Só um título")

    assert "error" in out
    assert "path" not in out
    pdf_dir = documents_root
    assert not pdf_dir.exists() or list(pdf_dir.glob("*.pdf")) == []
