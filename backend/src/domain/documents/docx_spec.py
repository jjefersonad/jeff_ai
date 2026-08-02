"""Spec de conteúdo de um documento Word (`.docx`) a ser criado."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar, Union

from src.domain.documents.blocks import ImageRef, Table
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


DocxBlock = Union[Heading, Paragraph, ListBlock, Table, ImageRef]


@dataclass(frozen=True)
class DocxSpec:
    """Documento Word a criar: um título e uma sequência ordenada de blocos."""

    kind: ClassVar[str] = "docx"
    extension: ClassVar[str] = ".docx"

    title: str
    blocks: tuple[DocxBlock, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        """Valida o título e os tipos dos blocos."""
        if not isinstance(self.title, str) or not self.title.strip():
            raise DomainError("DocxSpec.title é obrigatório e não pode ser vazio.")
        object.__setattr__(self, "title", self.title.strip())
        blocks = tuple(self.blocks)
        if not blocks:
            raise DomainError("DocxSpec.blocks deve conter ao menos um bloco.")
        allowed = (Heading, Paragraph, ListBlock, Table, ImageRef)
        if not all(isinstance(block, allowed) for block in blocks):
            raise DomainError("DocxSpec.blocks contém um tipo de bloco não suportado.")
        object.__setattr__(self, "blocks", blocks)

    def metadata(self) -> dict[str, object]:
        """Retorna os metadados do documento para o resultado da geração."""
        return {"kind": self.kind, "title": self.title, "block_count": len(self.blocks)}
