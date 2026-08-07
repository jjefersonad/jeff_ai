"""Adapters de infraestrutura para geração de documentos (docx/xlsx/pptx/pdf).

Writers Office legados usam bibliotecas nativas; o caminho canônico de
DOCX/XLSX/PPTX/PDF é o pipeline HTML (`Html*Converter` / WeasyPrint).
"""
from src.infrastructure.documents.docx_writer import DocxWriter
from src.infrastructure.documents.html_docx_converter import HtmlDocxConverter
from src.infrastructure.documents.html_pptx_converter import HtmlPptxConverter
from src.infrastructure.documents.html_template_repository import (
    FilesystemHtmlTemplateRepository,
)
from src.infrastructure.documents.html_xlsx_converter import HtmlXlsxConverter
from src.infrastructure.documents.pptx_writer import PptxWriter
from src.infrastructure.documents.weasyprint_pdf_converter import WeasyPrintPdfConverter
from src.infrastructure.documents.xlsx_writer import XlsxWriter

__all__ = [
    "DocxWriter",
    "FilesystemHtmlTemplateRepository",
    "HtmlDocxConverter",
    "HtmlPptxConverter",
    "HtmlXlsxConverter",
    "PptxWriter",
    "WeasyPrintPdfConverter",
    "XlsxWriter",
]
