"""Domínio de documentos Office — specs de conteúdo puros (docx/xlsx/pptx).

Entidades e value objects imutáveis que descrevem *o que* criar, sem conhecer as
bibliotecas de geração (python-docx/openpyxl/python-pptx) nem I/O. A validação de
invariantes acontece na construção (levanta `DomainError`).
"""
from src.domain.documents.blocks import ImageRef, Table
from src.domain.documents.document_result import DocumentResult
from src.domain.documents.document_spec import DocumentSpec
from src.domain.documents.docx_spec import (
    DocxBlock,
    DocxSpec,
    Heading,
    ListBlock,
    Paragraph,
)
from src.domain.documents.pptx_spec import (
    BulletSlide,
    ImageSlide,
    PptxSpec,
    Slide,
    TableSlide,
    TitleSlide,
)
from src.domain.documents.xlsx_spec import CellValue, Sheet, XlsxSpec

__all__ = [
    "BulletSlide",
    "CellValue",
    "DocumentResult",
    "DocumentSpec",
    "DocxBlock",
    "DocxSpec",
    "Heading",
    "ImageRef",
    "ImageSlide",
    "ListBlock",
    "Paragraph",
    "PptxSpec",
    "Sheet",
    "Slide",
    "Table",
    "TableSlide",
    "TitleSlide",
    "XlsxSpec",
]
