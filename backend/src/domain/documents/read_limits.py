"""Política de truncamento da leitura de documentos.

Vive no domínio, e não nos adapters, porque decidir *quanto* conteúdo cabe na
janela do modelo é regra de negócio — não detalhe da biblioteca de parsing. Os
adapters recebem os limites e reportam o truncamento; nunca os definem.
"""
from __future__ import annotations

from dataclasses import dataclass

from src.domain.shared.errors import DomainError

# Tetos de partida (design `document-reading-tools`): um `.xlsx` de milhões de
# células ou um `.pdf` de centenas de páginas estouram a janela do modelo.
_DEFAULT_MAX_CHARS = 200_000
_DEFAULT_MAX_CELLS = 50_000
_DEFAULT_MAX_UNITS = 500


@dataclass(frozen=True)
class ReadLimits:
    """Tetos de conteúdo aplicados a uma leitura.

    `max_chars` limita o texto acumulado do documento inteiro; `max_cells` limita
    as células de uma planilha; `max_units` limita páginas (`.pdf`) ou slides
    (`.pptx`). Todos devem ser positivos.
    """

    max_chars: int = _DEFAULT_MAX_CHARS
    max_cells: int = _DEFAULT_MAX_CELLS
    max_units: int = _DEFAULT_MAX_UNITS

    def __post_init__(self) -> None:
        """Valida que todos os tetos são positivos."""
        for name in ("max_chars", "max_cells", "max_units"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise DomainError(f"ReadLimits.{name} deve ser um inteiro positivo.")


class ReadBudget:
    """Orçamento de leitura consumido incrementalmente por um adapter.

    Permite parar de acumular conteúdo assim que um teto é atingido, em vez de
    materializar o documento inteiro para só então truncar. Mutável de propósito:
    é um acumulador, não um value object.
    """

    def __init__(self, limits: ReadLimits) -> None:
        """Inicia o orçamento zerado a partir dos limites informados."""
        self._limits = limits
        self._chars = 0
        self._cells = 0
        self._units = 0
        self._truncated = False

    @property
    def truncated(self) -> bool:
        """Informa se algum teto foi atingido durante a leitura."""
        return self._truncated

    def take_text(self, text: str) -> str:
        """Consome `text` do orçamento de caracteres, truncando-o se necessário.

        Retorna o texto que coube. Uma vez esgotado o orçamento, devolve string
        vazia e marca a leitura como truncada.
        """
        remaining = self._limits.max_chars - self._chars
        if remaining <= 0:
            self._truncated = True
            return ""
        if len(text) > remaining:
            self._truncated = True
            self._chars = self._limits.max_chars
            return text[:remaining]
        self._chars += len(text)
        return text

    def take_cell(self) -> bool:
        """Consome uma célula do orçamento; `False` quando o teto foi atingido."""
        if self._cells >= self._limits.max_cells:
            self._truncated = True
            return False
        self._cells += 1
        return True

    def take_unit(self) -> bool:
        """Consome uma página/slide do orçamento; `False` quando o teto foi atingido."""
        if self._units >= self._limits.max_units:
            self._truncated = True
            return False
        self._units += 1
        return True
