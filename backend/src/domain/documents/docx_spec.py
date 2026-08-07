"""Spec de conteúdo de um documento Word (`.docx`) a ser criado."""
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
from src.domain.documents.markdown_table import contains_markdown_table
from src.domain.shared.errors import DomainError

_MARKDOWN_TABLE_ERROR = (
    'DocxSpec: parágrafo contém tabela Markdown; use type="table" com rows '
    "(e header opcional) em vez de sintaxe | col | em paragraph."
)

# Re-export para importadores que ainda leem os VOs via docx_spec.
__all__ = [
    "DocxBlock",
    "DocxSpec",
    "Heading",
    "ImageRef",
    "ListBlock",
    "Paragraph",
    "Table",
]

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
        for block in blocks:
            if isinstance(block, Paragraph) and contains_markdown_table(block.text):
                raise DomainError(_MARKDOWN_TABLE_ERROR)
        object.__setattr__(self, "blocks", blocks)

    def metadata(self) -> dict[str, object]:
        """Retorna os metadados do documento para o resultado da geração."""
        return {"kind": self.kind, "title": self.title, "block_count": len(self.blocks)}
