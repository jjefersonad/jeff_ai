"""Adapters de infraestrutura para geração de documentos Office (docx/xlsx/pptx).

Cada writer implementa `DocumentWriterPort` usando uma biblioteca Python nativa
(python-docx/openpyxl/python-pptx), sem depender de binários externos.
"""
from src.infrastructure.documents.docx_writer import DocxWriter
from src.infrastructure.documents.pptx_writer import PptxWriter
from src.infrastructure.documents.xlsx_writer import XlsxWriter

__all__ = ["DocxWriter", "PptxWriter", "XlsxWriter"]
