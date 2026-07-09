"""Spec de conteúdo de uma planilha (`.xlsx`) a ser criada."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar, Union

from src.domain.shared.errors import DomainError

CellValue = Union[str, int, float, None]


@dataclass(frozen=True)
class Sheet:
    """Uma aba da planilha: nome, linhas de células e formatação básica.

    `rows` é uma sequência de linhas; cada célula é texto, número ou vazio
    (`None`). Uma célula string iniciada por `=` é interpretada como fórmula pelo
    writer. `header` deixa a primeira linha em negrito. `column_widths` define a
    largura das colunas (em ordem). `number_formats` mapeia índice de coluna
    (base 0) para um formato numérico (ex.: `"0.00"`).
    """

    name: str
    rows: tuple[tuple[CellValue, ...], ...] = field(default_factory=tuple)
    header: bool = False
    column_widths: tuple[float, ...] | None = None
    number_formats: tuple[tuple[int, str], ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        """Valida o nome, os tipos das células e a formatação."""
        if not isinstance(self.name, str) or not self.name.strip():
            raise DomainError("Sheet.name é obrigatório e não pode ser vazio.")
        object.__setattr__(self, "name", self.name.strip())

        rows = tuple(tuple(row) for row in self.rows)
        for row in rows:
            if any(not isinstance(cell, str | int | float | None) for cell in row):
                raise DomainError("Sheet.rows só aceita str, int, float ou None.")
        object.__setattr__(self, "rows", rows)

        if self.column_widths is not None and any(w <= 0 for w in self.column_widths):
            raise DomainError("Sheet.column_widths deve conter apenas valores positivos.")

        if any(col < 0 for col, _ in self.number_formats):
            raise DomainError("Sheet.number_formats usa índices de coluna >= 0.")


@dataclass(frozen=True)
class XlsxSpec:
    """Planilha a criar: uma ou mais abas."""

    kind: ClassVar[str] = "xlsx"
    extension: ClassVar[str] = ".xlsx"

    sheets: tuple[Sheet, ...]

    def __post_init__(self) -> None:
        """Valida que há pelo menos uma aba e que todas são `Sheet`."""
        sheets = tuple(self.sheets)
        if not sheets:
            raise DomainError("XlsxSpec.sheets deve conter ao menos uma aba.")
        if not all(isinstance(sheet, Sheet) for sheet in sheets):
            raise DomainError("XlsxSpec.sheets deve conter apenas objetos Sheet.")
        object.__setattr__(self, "sheets", sheets)

    def metadata(self) -> dict[str, object]:
        """Retorna os metadados da planilha para o resultado da geração."""
        return {"kind": self.kind, "sheets": [sheet.name for sheet in self.sheets]}
