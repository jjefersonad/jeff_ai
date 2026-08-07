"""Testes de enforcement Markdown-table em DocxSpec (fix-docx-table-markdown)."""
from __future__ import annotations

import pytest

from src.domain.documents import DocxSpec, Paragraph
from src.domain.shared.errors import DomainError

_MD_TABLE = "| A | B |\n|---|---|\n| 1 | 2 |"


def test_docx_spec_rejects_markdown_table_paragraph() -> None:
    with pytest.raises(DomainError):
        DocxSpec(title="Relatório", blocks=(Paragraph(text=_MD_TABLE),))


def test_docx_spec_accepts_prose_and_isolated_pipe() -> None:
    prose = DocxSpec(
        title="Relatório",
        blocks=(Paragraph(text="Este relatório resume o status."),),
    )
    assert prose.title == "Relatório"

    with_pipe = DocxSpec(
        title="Escolha",
        blocks=(Paragraph(text="escolha A | B"),),
    )
    assert with_pipe.blocks[0].text == "escolha A | B"  # type: ignore[union-attr]


def test_docx_spec_error_mentions_type_table_and_rows() -> None:
    with pytest.raises(DomainError, match=r'type=["\']table["\'].*rows|rows.*type=["\']table["\']') as exc_info:
        DocxSpec(title="Relatório", blocks=(Paragraph(text=_MD_TABLE),))
    msg = str(exc_info.value)
    assert 'type="table"' in msg or "type='table'" in msg
    assert "rows" in msg
