"""Testes do detector `contains_markdown_table` (fix-docx-table-markdown)."""
from __future__ import annotations

from src.domain.documents.markdown_table import contains_markdown_table


def test_contains_markdown_table_true_for_gfm_table() -> None:
    text = "| A | B |\n|---|---|\n| 1 | 2 |"
    assert contains_markdown_table(text) is True


def test_contains_markdown_table_true_for_pipe_grid_without_separator() -> None:
    text = "| Mês | Receita |\n| Jan | 12000 |"
    assert contains_markdown_table(text) is True


def test_contains_markdown_table_false_for_plain_prose() -> None:
    text = "Este relatório resume o status do projeto no trimestre."
    assert contains_markdown_table(text) is False


def test_contains_markdown_table_false_for_isolated_pipe() -> None:
    text = "escolha A | B"
    assert contains_markdown_table(text) is False
