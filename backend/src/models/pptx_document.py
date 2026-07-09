"""Schema Pydantic para a entrada estruturada da tool `create_pptx_presentation`.

Modela o conteúdo de uma apresentação (sequência de slides) com um formato
tolerante (campos opcionais viram default no domínio). Vive em `models/`
porque é só contrato de borda da tool — não contém regra de negócio.
"""
from __future__ import annotations

from typing import List

from pydantic import BaseModel, ConfigDict, Field


class PptxTitleSlideInput(BaseModel):
    """Slide de título (capa), com subtítulo opcional."""

    type: str = Field(default="title", description="Tipo do slide: 'title'.")
    title: str = Field(description="Título do slide.")
    subtitle: str | None = Field(default=None, description="Subtítulo opcional.")


class PptxBulletSlideInput(BaseModel):
    """Slide de conteúdo com título e bullets."""

    type: str = Field(default="bullets", description="Tipo do slide: 'bullets'.")
    title: str = Field(description="Título do slide.")
    bullets: List[str] = Field(description="Itens do slide (ao menos um).")


class PptxImageSlideInput(BaseModel):
    """Slide com imagem embutida e título opcional."""

    type: str = Field(default="image", description="Tipo do slide: 'image'.")
    title: str | None = Field(default=None, description="Título opcional do slide.")
    path: str = Field(description="Caminho da imagem em disco.")
    width_inches: float | None = Field(
        default=None,
        description="Largura da imagem em polegadas (omitir = tamanho original).",
    )


class PptxTableSlideInput(BaseModel):
    """Slide com tabela simples e título opcional."""

    type: str = Field(default="table", description="Tipo do slide: 'table'.")
    title: str | None = Field(default=None, description="Título opcional do slide.")
    rows: List[List[str]] = Field(
        description="Linhas da tabela (retangular, ao menos uma).",
    )
    header: bool = Field(
        default=True,
        description="Se True, a primeira linha fica em negrito.",
    )


class PptxSlideInput(BaseModel):
    """Slide genérico da apresentação — discriminated union leve via `type`."""

    type: str = Field(
        description="Tipo do slide: 'title' | 'bullets' | 'image' | 'table'.",
    )
    title: str | None = Field(default=None, description="Título (todos os tipos).")
    subtitle: str | None = Field(
        default=None,
        description="Subtítulo (title).",
    )
    bullets: List[str] | None = Field(
        default=None,
        description="Bullets (bullets).",
    )
    path: str | None = Field(
        default=None,
        description="Caminho da imagem (image).",
    )
    width_inches: float | None = Field(
        default=None,
        description="Largura em polegadas (image).",
    )
    rows: List[List[str]] | None = Field(
        default=None,
        description="Linhas (table).",
    )
    header: bool | None = Field(
        default=None,
        description="Primeira linha em negrito? (table).",
    )

    model_config = ConfigDict(
        json_schema_extra={"example": {"type": "title", "title": "Apresentação"}}
    )


class PptxDocumentInput(BaseModel):
    """Schema estruturado de entrada para `create_pptx_presentation`.

    Aceita uma sequência de slides discriminados pelo campo `type`. O conversor
    da tool descarta slides inválidos (sem campos obrigatórios) em vez de falhar,
    mantendo o contrato tolerante.
    """

    slides: List[PptxSlideInput] = Field(
        description="Sequência de slides da apresentação (ao menos um).",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "slides": [
                    {"type": "title", "title": "Roadmap 2026", "subtitle": "Time de IA"},
                    {
                        "type": "bullets",
                        "title": "Objetivos",
                        "bullets": ["Reduzir latência", "Aumentar cobertura"],
                    },
                    {"type": "image", "title": "Time", "path": "/tmp/team.png"},
                ]
            }
        }
    )
