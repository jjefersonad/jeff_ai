"""Testes de ownership em `create_xlsx_spreadsheet` (media-ownership-authorization REQ-001)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

import src.tools.create_xlsx_spreadsheet_tool as xlsx_tool
from src.domain.documents.document_result import DocumentResult
from src.models.xlsx_document import XlsxDocumentInput, XlsxSheetInput


class _FakeRender:
    def __init__(self, result: DocumentResult) -> None:
        self._result = result

    async def execute(self, **_kwargs: object) -> DocumentResult:
        return self._result


def _payload() -> XlsxDocumentInput:
    return XlsxDocumentInput(sheets=[XlsxSheetInput(name="Vendas", rows=[["a", 1]])])


async def test_records_ownership_with_kind_and_basename(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    result = DocumentResult(
        path=str(tmp_path / "20260708120000.xlsx"),
        url="/api/files/xlsx/20260708120000.xlsx",
        metadata={"kind": "xlsx"},
    )
    monkeypatch.setattr(xlsx_tool, "require_user_docs_dir", AsyncMock(return_value=tmp_path))
    monkeypatch.setattr(xlsx_tool, "_build_xlsx_render", lambda _output_dir=None: _FakeRender(result))
    record = AsyncMock()
    monkeypatch.setattr(xlsx_tool, "record_ownership", record)

    out = await xlsx_tool.create_xlsx_spreadsheet.coroutine(_payload())

    assert out == {"path": result.path, "url": result.url, "metadata": result.metadata}
    record.assert_awaited_once_with(kind="xlsx", filename="20260708120000.xlsx")


async def test_ownership_failure_is_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    result = DocumentResult(
        path=str(tmp_path / "20260708120000.xlsx"),
        url="/api/files/xlsx/20260708120000.xlsx",
        metadata={"kind": "xlsx"},
    )
    monkeypatch.setattr(xlsx_tool, "require_user_docs_dir", AsyncMock(return_value=tmp_path))
    monkeypatch.setattr(xlsx_tool, "_build_xlsx_render", lambda _output_dir=None: _FakeRender(result))
    monkeypatch.setattr(
        xlsx_tool, "record_ownership", AsyncMock(side_effect=RuntimeError("db down"))
    )

    out = await xlsx_tool.create_xlsx_spreadsheet.coroutine(_payload())

    assert "error" in out
    assert "path" not in out
