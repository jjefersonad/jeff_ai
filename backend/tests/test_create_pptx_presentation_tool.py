"""Testes de ownership em `create_pptx_presentation` (media-ownership-authorization REQ-001)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

import src.tools.create_pptx_presentation_tool as pptx_tool
from src.domain.documents.document_result import DocumentResult
from src.models.pptx_document import PptxDocumentInput, PptxSlideInput


class _FakeRender:
    def __init__(self, result: DocumentResult) -> None:
        self._result = result

    async def execute(self, **_kwargs: object) -> DocumentResult:
        return self._result


def _payload() -> PptxDocumentInput:
    return PptxDocumentInput(slides=[PptxSlideInput(type="title", title="Capa")])


async def test_records_ownership_with_kind_and_basename(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    result = DocumentResult(
        path=str(tmp_path / "20260708120000.pptx"),
        url="/api/files/pptx/20260708120000.pptx",
        metadata={"kind": "pptx"},
    )
    monkeypatch.setattr(pptx_tool, "_build_pptx_render", lambda: _FakeRender(result))
    record = AsyncMock()
    monkeypatch.setattr(pptx_tool, "record_ownership", record)

    out = await pptx_tool.create_pptx_presentation.coroutine(_payload())

    assert out == {"path": result.path, "url": result.url, "metadata": result.metadata}
    record.assert_awaited_once_with(kind="pptx", filename="20260708120000.pptx")


async def test_ownership_failure_is_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    result = DocumentResult(
        path=str(tmp_path / "20260708120000.pptx"),
        url="/api/files/pptx/20260708120000.pptx",
        metadata={"kind": "pptx"},
    )
    monkeypatch.setattr(pptx_tool, "_build_pptx_render", lambda: _FakeRender(result))
    monkeypatch.setattr(
        pptx_tool, "record_ownership", AsyncMock(side_effect=RuntimeError("db down"))
    )

    out = await pptx_tool.create_pptx_presentation.coroutine(_payload())

    assert "error" in out
    assert "path" not in out
