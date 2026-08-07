"""Unit: WeasyPrintPdfConverter (html-document-tools-task-pdf-1)."""
from __future__ import annotations

import pytest

from src.domain.shared.errors import DomainError
from src.infrastructure.documents.weasyprint_pdf_converter import WeasyPrintPdfConverter


@pytest.mark.asyncio
async def test_convert_html_to_pdf_bytes() -> None:
    converter = WeasyPrintPdfConverter()
    payload = await converter.convert(
        html="<html><body><h1>Hi</h1></body></html>",
        css="h1 { color: black; }",
        kind="pdf",
    )
    assert payload[:4] == b"%PDF"


@pytest.mark.asyncio
async def test_convert_rejects_non_pdf_kind() -> None:
    converter = WeasyPrintPdfConverter()
    with pytest.raises(DomainError, match="pdf"):
        await converter.convert(html="<p>x</p>", css=None, kind="docx")
