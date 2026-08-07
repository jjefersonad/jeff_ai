"""Testes do núcleo RenderHtmlDocument (html-document-tools-task-pipeline-1)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from src.application.ports.html_document_converter import HtmlDocumentConverter
from src.application.use_cases.render_html_document import RenderHtmlDocument
from src.domain.shared.errors import DomainError


class _FakeConverter(HtmlDocumentConverter):
    def __init__(
        self,
        *,
        payload: bytes = b"%PDF-fake",
        error: Exception | None = None,
        capture: list[dict[str, Any]] | None = None,
    ) -> None:
        self._payload = payload
        self._error = error
        self._capture = capture if capture is not None else []

    async def convert(self, *, html: str, css: str | None, kind: str) -> bytes:
        self._capture.append({"html": html, "css": css, "kind": kind})
        if self._error is not None:
            raise self._error
        return self._payload


@pytest.fixture
def output_dir(tmp_path: Path) -> Path:
    return tmp_path / "documents"


@pytest.mark.asyncio
async def test_invalid_kind_rejected_without_files(output_dir: Path) -> None:
    """Unit-1: kind fora do conjunto falha sem criar arquivos."""
    ownership_calls: list[tuple[str, str]] = []
    use_case = RenderHtmlDocument(
        converters={"pdf": _FakeConverter()},
        output_base_dir=output_dir,
        record_ownership=lambda kind, filename: ownership_calls.append((kind, filename)),
    )

    with pytest.raises(DomainError, match="kind"):
        await use_case.execute(html="<p>hi</p>", kind="exe")

    assert not output_dir.exists() or not any(output_dir.rglob("*"))
    assert ownership_calls == []


@pytest.mark.asyncio
async def test_converter_failure_leaves_no_partial_nor_ownership(output_dir: Path) -> None:
    """Unit-2: falha do converter não deixa arquivo nem carimba ownership."""
    ownership_calls: list[tuple[str, str]] = []
    use_case = RenderHtmlDocument(
        converters={"pdf": _FakeConverter(error=RuntimeError("boom"))},
        output_base_dir=output_dir,
        record_ownership=lambda kind, filename: ownership_calls.append((kind, filename)),
    )

    with pytest.raises(RuntimeError, match="boom"):
        await use_case.execute(html="<p>hi</p>", kind="pdf")

    pdf_dir = output_dir / "pdf"
    assert not pdf_dir.exists() or list(pdf_dir.glob("*")) == []
    html_dir = output_dir / "html"
    assert not html_dir.exists()
    assert ownership_calls == []


@pytest.mark.asyncio
async def test_script_and_javascript_uri_are_sanitized_before_convert(
    output_dir: Path,
) -> None:
    """Unit-3: script/javascript: não chegam ao converter."""
    capture: list[dict[str, object]] = []
    use_case = RenderHtmlDocument(
        converters={"pdf": _FakeConverter(capture=capture)},
        output_base_dir=output_dir,
    )
    dirty = (
        '<p>ok</p><script>alert(1)</script>'
        '<a href="javascript:alert(1)">x</a>'
        '<a href="https://example.com">y</a>'
    )
    result = await use_case.execute(html=dirty, kind="pdf", title="T")

    assert result.metadata["kind"] == "pdf"
    assert Path(result.path).is_file()
    assert not (output_dir / "html").exists()
    assert len(capture) == 1
    sent = str(capture[0]["html"])
    assert "<script" not in sent.lower()
    assert "javascript:" not in sent.lower()
    assert "alert(1)" not in sent
    assert "https://example.com" in sent
    assert "<p>ok</p>" in sent
