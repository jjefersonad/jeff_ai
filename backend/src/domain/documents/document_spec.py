"""Tipo união `DocumentSpec` — qualquer spec de documento suportado."""
from __future__ import annotations

from typing import Union

from src.domain.documents.docx_spec import DocxSpec
from src.domain.documents.pptx_spec import PptxSpec
from src.domain.documents.xlsx_spec import XlsxSpec

DocumentSpec = Union[DocxSpec, XlsxSpec, PptxSpec]
