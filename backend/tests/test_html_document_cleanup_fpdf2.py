"""Cleanup fpdf2 / PdfWriter (html-document-tools-task-cleanup-1)."""
from __future__ import annotations

from pathlib import Path

import tomllib

import src.tools.create_pdf_document_tool as pdf_tool
from src.infrastructure.documents.weasyprint_pdf_converter import WeasyPrintPdfConverter

_BACKEND = Path(__file__).resolve().parents[1]
_REPO = _BACKEND.parent


def test_pyproject_and_dockerfile_have_no_fpdf2_runtime_dep() -> None:
    """Unit-1: pyproject + Dockerfile.backend sem fpdf2 de produção."""
    data = tomllib.loads((_BACKEND / "pyproject.toml").read_text(encoding="utf-8"))
    deps = data["project"]["dependencies"]
    assert not any("fpdf2" in dep for dep in deps), deps

    dockerfile = (_BACKEND / "Dockerfile.backend").read_text(encoding="utf-8")
    assert "fpdf2" not in dockerfile


def test_create_pdf_factory_uses_weasyprint_not_pdf_writer() -> None:
    """Unit-2: factory canônica → WeasyPrintPdfConverter, não PdfWriter."""
    render = pdf_tool._build_pdf_render()
    converter = render._converters["pdf"]
    assert isinstance(converter, WeasyPrintPdfConverter)
    src = Path(pdf_tool.__file__).read_text(encoding="utf-8")
    assert "PdfWriter" not in src
    assert "WeasyPrintPdfConverter" in src
