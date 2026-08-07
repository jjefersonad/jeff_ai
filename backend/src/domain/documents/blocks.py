"""Value objects de conteúdo compartilhados entre formatos de documento."""
from __future__ import annotations

from dataclasses import dataclass

from src.domain.shared.errors import DomainError


@dataclass(frozen=True)
class Heading:
    """Título/seção com nível hierárquico (1 a 9)."""

    text: str
    level: int = 1

    def __post_init__(self) -> None:
        """Valida o texto e o nível do heading."""
        if not isinstance(self.text, str) or not self.text.strip():
            raise DomainError("Heading.text é obrigatório e não pode ser vazio.")
        object.__setattr__(self, "text", self.text.strip())
        if not 1 <= self.level <= 9:
            raise DomainError("Heading.level deve estar entre 1 e 9.")


@dataclass(frozen=True)
class Paragraph:
    """Parágrafo de texto simples."""

    text: str

    def __post_init__(self) -> None:
        """Valida que o parágrafo não é vazio."""
        if not isinstance(self.text, str) or not self.text.strip():
            raise DomainError("Paragraph.text é obrigatório e não pode ser vazio.")
        object.__setattr__(self, "text", self.text.strip())


@dataclass(frozen=True)
class ListBlock:
    """Lista de itens, ordenada (numerada) ou não (marcadores)."""

    items: tuple[str, ...]
    ordered: bool = False

    def __post_init__(self) -> None:
        """Normaliza e valida os itens da lista (nenhum vazio)."""
        items = tuple(item.strip() for item in self.items if isinstance(item, str))
        if len(items) != len(self.items) or not items:
            raise DomainError("ListBlock.items deve conter apenas strings não vazias.")
        if any(not item for item in items):
            raise DomainError("ListBlock.items não pode conter itens vazios.")
        object.__setattr__(self, "items", items)


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
