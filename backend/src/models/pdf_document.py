"""Schema Pydantic para a entrada estruturada da tool `create_pdf_document`.

Mesmo contrato de blocos do docx (heading/paragraph/list/table/image) — vive em
`models/` porque é só contrato de borda da tool.
"""
from __future__ import annotations

from typing import List

from pydantic import BaseModel, ConfigDict, Field


class PdfBlockInput(BaseModel):
    """Bloco genérico do PDF — discriminated union leve via `type`."""

    type: str = Field(
        description="Tipo do bloco: 'heading' | 'paragraph' | 'list' | 'table' | 'image'.",
    )
    text: str | None = Field(
        default=None,
        description="Texto (heading/paragraph). Obrigatório para heading/paragraph.",
    )
    level: int | None = Field(
        default=None,
        description="Nível do heading (1 a 9). Usado quando type='heading'.",
    )
    items: List[str] | None = Field(
        default=None,
        description="Itens da lista. Usado quando type='list'.",
    )
    ordered: bool | None = Field(
        default=None,
        description="Lista ordenada? Usado quando type='list'.",
    )
    rows: List[List[str]] | None = Field(
        default=None,
        description="Linhas da tabela. Usado quando type='table'.",
    )
    header: bool | None = Field(
        default=None,
        description="Primeira linha em negrito? Usado quando type='table'.",
    )
    path: str | None = Field(
        default=None,
        description="Caminho da imagem. Usado quando type='image'.",
    )
    width_inches: float | None = Field(
        default=None,
        description="Largura da imagem em polegadas. Usado quando type='image'.",
    )


class PdfDocumentInput(BaseModel):
    """Schema estruturado de entrada para `create_pdf_document`."""

    title: str = Field(description="Título principal do documento.")
    blocks: List[PdfBlockInput] = Field(
        default_factory=list,
        description="Sequência ordenada de blocos do documento.",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "title": "Relatório de Status",
                "blocks": [
                    {"type": "heading", "text": "Resumo", "level": 1},
                    {"type": "paragraph", "text": "Este relatório resume os resultados."},
                ],
            }
        }
    )
