"""Testes de ownership em `create_docx_document` (media-ownership-authorization REQ-001)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

import src.tools.create_docx_document_tool as docx_tool
from src.domain.documents.document_result import DocumentResult
from src.models.docx_document import DocxBlockInput, DocxDocumentInput


class _FakeRender:
    def __init__(self, result: DocumentResult) -> None:
        self._result = result

    async def execute(self, **_kwargs: object) -> DocumentResult:
        return self._result


def _payload() -> DocxDocumentInput:
    return DocxDocumentInput(
        title="Relatório",
        blocks=[DocxBlockInput(type="paragraph", text="corpo")],
    )


async def test_records_ownership_with_kind_and_basename(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    result = DocumentResult(
        path=str(tmp_path / "20260708120000.docx"),
        url="/api/files/docx/20260708120000.docx",
        metadata={"kind": "docx"},
    )
    monkeypatch.setattr(docx_tool, "require_user_docs_dir", AsyncMock(return_value=tmp_path))
    monkeypatch.setattr(docx_tool, "_build_docx_render", lambda _output_dir=None: _FakeRender(result))
    record = AsyncMock()
    monkeypatch.setattr(docx_tool, "record_ownership", record)

    out = await docx_tool.create_docx_document.coroutine(_payload())

    assert out == {"path": result.path, "url": result.url, "metadata": result.metadata}
    record.assert_awaited_once_with(kind="docx", filename="20260708120000.docx")


async def test_ownership_failure_is_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """media-1 REQ-001: falha ao registrar ownership impede sucesso (fail-closed)."""
    result = DocumentResult(
        path=str(tmp_path / "20260708120000.docx"),
        url="/api/files/docx/20260708120000.docx",
        metadata={"kind": "docx"},
    )
    monkeypatch.setattr(docx_tool, "require_user_docs_dir", AsyncMock(return_value=tmp_path))
    monkeypatch.setattr(docx_tool, "_build_docx_render", lambda _output_dir=None: _FakeRender(result))
    monkeypatch.setattr(
        docx_tool, "record_ownership", AsyncMock(side_effect=RuntimeError("db down"))
    )

    out = await docx_tool.create_docx_document.coroutine(_payload())

    assert "error" in out
    assert "path" not in out
