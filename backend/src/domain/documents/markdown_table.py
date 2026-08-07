"""Detecção de tabelas Markdown embutidas em texto de parágrafo.

Heurística conservadora (design fix-docx-table-markdown):
- true se ≥2 linhas de dados no formato de linha de tabela (≥2 células), ou
  uma linha de cabeçalho + linha separadora GFM (`|---|`, `:---:`, etc.);
- false para prosa e para um único `|` isolado em uma linha.
"""
from __future__ import annotations

import re

_SEPARATOR_RE = re.compile(
    r"^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$",
)
_CELL_SPLIT_RE = re.compile(r"\|")


def _is_table_data_row(line: str) -> bool:
    """Linha com ≥2 células não vazias separadas por `|`."""
    stripped = line.strip()
    if not stripped or _SEPARATOR_RE.match(stripped):
        return False
    # Remover pipes opcionais nas bordas antes de contar células.
    inner = stripped
    if inner.startswith("|"):
        inner = inner[1:]
    if inner.endswith("|"):
        inner = inner[:-1]
    cells = [c.strip() for c in _CELL_SPLIT_RE.split(inner)]
    nonempty = [c for c in cells if c]
    return len(nonempty) >= 2


def _is_separator_row(line: str) -> bool:
    return bool(_SEPARATOR_RE.match(line.strip()))


def contains_markdown_table(text: str) -> bool:
    """Retorna True se `text` parece conter uma tabela Markdown multi-linha."""
    if not isinstance(text, str):
        return False
    lines = [ln for ln in text.strip().splitlines() if ln.strip()]
    if len(lines) < 2:
        return False

    data_rows = [_is_table_data_row(ln) for ln in lines]
    separators = [_is_separator_row(ln) for ln in lines]

    if sum(1 for is_data in data_rows if is_data) >= 2:
        return True

    # Cabeçalho + separator (ordem típica GFM).
    for i in range(len(lines) - 1):
        if data_rows[i] and separators[i + 1]:
            return True
    return False
