"""Value objects de conteúdo compartilhados entre formatos (tabela e imagem)."""
from __future__ import annotations

from dataclasses import dataclass

from src.domain.shared.errors import DomainError


@dataclass(frozen=True)
class Table:
    """Tabela retangular de células textuais, com linha de cabeçalho opcional.

    `rows` deve ser não vazia e retangular (todas as linhas com o mesmo número
    de colunas). As células são normalizadas para `str`.
    """

    rows: tuple[tuple[str, ...], ...]
    header: bool = True

    def __post_init__(self) -> None:
        """Normaliza as células para `str` e valida que a tabela é retangular."""
        rows = tuple(tuple(str(cell) for cell in row) for row in self.rows)
        if not rows:
            raise DomainError("Table.rows não pode ser vazia.")
        width = len(rows[0])
        if width == 0 or any(len(row) != width for row in rows):
            raise DomainError("Table.rows deve ser retangular e sem colunas vazias.")
        object.__setattr__(self, "rows", rows)


@dataclass(frozen=True)
class ImageRef:
    """Referência a uma imagem em disco a ser embutida no documento.

    `path` é obrigatório; `width_inches`, quando informado, deve ser positivo.
    """

    path: str
    width_inches: float | None = None

    def __post_init__(self) -> None:
        """Valida o caminho e a largura opcional da imagem."""
        if not isinstance(self.path, str) or not self.path.strip():
            raise DomainError("ImageRef.path é obrigatório e não pode ser vazio.")
        object.__setattr__(self, "path", self.path.strip())
        if self.width_inches is not None and self.width_inches <= 0:
            raise DomainError("ImageRef.width_inches deve ser positivo quando informado.")
