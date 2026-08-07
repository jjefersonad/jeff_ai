"""Spec de conteúdo de um documento PDF (`.pdf`) a ser criado."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar, Union

from src.domain.documents.blocks import (
    Heading,
    ImageRef,
    ListBlock,
    Paragraph,
    Table,
)
from src.domain.shared.errors import DomainError

PdfBlock = Union[Heading, Paragraph, ListBlock, Table, ImageRef]


@dataclass(frozen=True)
class PdfSpec:
    """Documento PDF a criar: um título e uma sequência ordenada de blocos."""

    kind: ClassVar[str] = "pdf"
    extension: ClassVar[str] = ".pdf"

    title: str
    blocks: tuple[PdfBlock, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        """Valida o título e os tipos dos blocos."""
        if not isinstance(self.title, str) or not self.title.strip():
            raise DomainError("PdfSpec.title é obrigatório e não pode ser vazio.")
        object.__setattr__(self, "title", self.title.strip())
        blocks = tuple(self.blocks)
        if not blocks:
            raise DomainError("PdfSpec.blocks deve conter ao menos um bloco.")
        allowed = (Heading, Paragraph, ListBlock, Table, ImageRef)
        if not all(isinstance(block, allowed) for block in blocks):
            raise DomainError("PdfSpec.blocks contém um tipo de bloco não suportado.")
        object.__setattr__(self, "blocks", blocks)

    def metadata(self) -> dict[str, object]:
        """Retorna os metadados do documento para o resultado da geração."""
        return {"kind": self.kind, "title": self.title, "block_count": len(self.blocks)}
