"""Testes da tool `create_pdf_document` (legado + pipeline HTML)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

import src.tools.create_pdf_document_tool as pdf_tool
from src.domain.documents.document_result import DocumentResult
from src.models.html_document_input import HtmlBlockInput, HtmlDocumentInput
from src.models.pdf_document import PdfBlockInput, PdfDocumentInput


class _FakeRender:
    def __init__(self, result: DocumentResult) -> None:
        self._result = result

    async def execute(self, **_kwargs: object) -> DocumentResult:
        return self._result


def _blocks_payload() -> PdfDocumentInput:
    return PdfDocumentInput(
        title="Relatório",
        blocks=[PdfBlockInput(type="paragraph", text="corpo")],
    )


async def test_tool_success_returns_path_url_metadata(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Unit: tool sucesso retorna path url metadata."""
    result = DocumentResult(
        path=str(tmp_path / "20260807120000.pdf"),
        url="http://localhost:3000/api/files/pdf/20260807120000.pdf",
        metadata={"kind": "pdf", "title": "Relatório"},
    )
    monkeypatch.setattr(pdf_tool, "_build_pdf_render", lambda: _FakeRender(result))
    monkeypatch.setattr(pdf_tool, "record_ownership", AsyncMock())

    out = await pdf_tool.create_pdf_document.coroutine(_blocks_payload())

    assert out["path"] == result.path
    assert "/api/files/pdf/" in out["url"]
    assert out["metadata"]["kind"] == "pdf"


async def test_tool_rejects_plain_string(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Unit: tool rejeita string simples."""
    called = AsyncMock()
    monkeypatch.setattr(pdf_tool, "_build_pdf_render", called)

    out = await pdf_tool.create_pdf_document.coroutine("Só um título")

    assert "error" in out
    assert "path" not in out
    assert "url" not in out
    called.assert_not_called()
    assert list(tmp_path.glob("*.pdf")) == []


async def test_tool_records_ownership_pdf(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Unit: tool carimba ownership pdf."""
    result = DocumentResult(
        path=str(tmp_path / "20260807120000.pdf"),
        url="/api/files/pdf/20260807120000.pdf",
        metadata={"kind": "pdf"},
    )
    monkeypatch.setattr(pdf_tool, "_build_pdf_render", lambda: _FakeRender(result))
    record = AsyncMock()
    monkeypatch.setattr(pdf_tool, "record_ownership", record)

    out = await pdf_tool.create_pdf_document.coroutine(_blocks_payload())

    assert out == {"path": result.path, "url": result.url, "metadata": result.metadata}
    record.assert_awaited_once_with(kind="pdf", filename="20260807120000.pdf")


async def test_ownership_failure_is_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Unit: falha de stamp é fail-closed."""
    result = DocumentResult(
        path=str(tmp_path / "20260807120000.pdf"),
        url="/api/files/pdf/20260807120000.pdf",
        metadata={"kind": "pdf"},
    )
    monkeypatch.setattr(pdf_tool, "_build_pdf_render", lambda: _FakeRender(result))
    monkeypatch.setattr(
        pdf_tool, "record_ownership", AsyncMock(side_effect=RuntimeError("db down"))
    )

    out = await pdf_tool.create_pdf_document.coroutine(_blocks_payload())

    assert "error" in out
    assert "path" not in out


async def test_legacy_blocks_still_resolve(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """PdfDocumentInput/HtmlDocumentInput com blocks ainda geram PDF."""
    monkeypatch.setattr(pdf_tool, "_documents_base_dir", lambda: tmp_path)
    monkeypatch.setattr(pdf_tool, "_document_url_prefix", lambda: "/api/files")
    monkeypatch.setattr(pdf_tool, "record_ownership", AsyncMock())

    out = await pdf_tool.create_pdf_document.coroutine(
        HtmlDocumentInput(
            title="Doc",
            blocks=[HtmlBlockInput(type="paragraph", text="olá")],
        )
    )

    assert "error" not in out
    assert out["metadata"]["kind"] == "pdf"
    assert Path(out["path"]).read_bytes()[:4] == b"%PDF"
