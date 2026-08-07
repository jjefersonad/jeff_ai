"""Converter HTML/CSS → PDF via WeasyPrint."""
from __future__ import annotations

from weasyprint import CSS, HTML

from src.application.ports.html_document_converter import HtmlDocumentConverter
from src.domain.shared.errors import DomainError


class WeasyPrintPdfConverter(HtmlDocumentConverter):
    """Implementação canônica de HTML→PDF para o pipeline de documentos."""

    async def convert(self, *, html: str, css: str | None, kind: str) -> bytes:
        if kind != "pdf":
            raise DomainError(
                f"WeasyPrintPdfConverter só suporta kind='pdf', recebeu {kind!r}."
            )
        stylesheets = [CSS(string=css)] if css and css.strip() else None
        return HTML(string=html).write_pdf(stylesheets=stylesheets)
