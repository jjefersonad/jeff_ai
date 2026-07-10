"""Domínio de documentos Office — specs de escrita e conteúdo de leitura.

Entidades e value objects imutáveis, sem conhecer as bibliotecas (python-docx/
openpyxl/python-pptx/pypdf) nem I/O. A validação de invariantes acontece na
construção (levanta `DomainError`).

Dois lados simétricos e deliberadamente separados:

- **Escrita** (`DocumentSpec` e seus blocos) descreve *o que criar*, e é estrita:
  um parágrafo vazio é erro de programação.
- **Leitura** (`DocumentContent` e seus blocos) descreve *o que se leu*, e é
  permissiva: um `.docx` real contém parágrafos vazios.
"""
from src.domain.documents.blocks import ImageRef, Table
from src.domain.documents.document_content import (
    READABLE_KINDS,
    ContentBlock,
    DocumentContent,
    HeadingBlock,
    PageContent,
    ParagraphBlock,
    ReadCellValue,
    ReadMetadata,
    SheetContent,
    SlideContent,
    TableBlock,
)
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
from src.domain.documents.read_limits import ReadBudget, ReadLimits
from src.domain.documents.xlsx_spec import CellValue, Sheet, XlsxSpec

__all__ = [
    "READABLE_KINDS",
    "BulletSlide",
    "CellValue",
    "ContentBlock",
    "DocumentContent",
    "DocumentResult",
    "DocumentSpec",
    "DocxBlock",
    "DocxSpec",
    "Heading",
    "HeadingBlock",
    "ImageRef",
    "ImageSlide",
    "ListBlock",
    "PageContent",
    "Paragraph",
    "ParagraphBlock",
    "PptxSpec",
    "ReadBudget",
    "ReadCellValue",
    "ReadLimits",
    "ReadMetadata",
    "Sheet",
    "SheetContent",
    "Slide",
    "SlideContent",
    "Table",
    "TableBlock",
    "TableSlide",
    "TitleSlide",
    "XlsxSpec",
]
