"""Adapters de infraestrutura para geração de documentos (docx/xlsx/pptx/pdf).

Cada writer implementa `DocumentWriterPort` usando uma biblioteca Python nativa
(python-docx/openpyxl/python-pptx/fpdf2), sem depender de binários externos.
"""
from src.infrastructure.documents.docx_writer import DocxWriter
from src.infrastructure.documents.pdf_writer import PdfWriter
from src.infrastructure.documents.pptx_writer import PptxWriter
from src.infrastructure.documents.xlsx_writer import XlsxWriter

__all__ = ["DocxWriter", "PdfWriter", "PptxWriter", "XlsxWriter"]
