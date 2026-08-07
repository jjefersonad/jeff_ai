"""Schema unificado de entrada para geração de documentos via HTML/pipeline.

Modos (mutuamente exclusivos onde indicado):
- `html` (+ `css` opcional)
- `template` + `data`
- `title` + `blocks` (legado, convertido para HTML semântico)
"""
from __future__ import annotations

from typing import Any, List

from pydantic import BaseModel, ConfigDict, Field, model_validator


class HtmlBlockInput(BaseModel):
    """Bloco legado — mesmos tipos do docx/pdf (heading/paragraph/list/table/image)."""

    type: str = Field(
        description="Tipo: 'heading' | 'paragraph' | 'list' | 'table' | 'image'.",
    )
    text: str | None = None
    level: int | None = None
    items: List[str] | None = None
    ordered: bool | None = None
    rows: List[List[str]] | None = None
    header: bool | None = None
    path: str | None = None
    width_inches: float | None = None


class HtmlDocumentInput(BaseModel):
    """Entrada canônica das tools de documento no pipeline HTML."""

    title: str | None = Field(default=None, description="Título (modo blocks ou metadata).")
    html: str | None = Field(default=None, description="HTML livre (documento ou fragmento).")
    css: str | None = Field(default=None, description="CSS opcional junto com html.")
    template: str | None = Field(default=None, description="Nome do template (ex.: proposal).")
    data: dict[str, Any] | None = Field(
        default=None,
        description="Dados do template (Jinja2).",
    )
    blocks: List[HtmlBlockInput] = Field(
        default_factory=list,
        description="Blocos legados (heading/paragraph/list/table/image).",
    )
    from_preview: str | None = Field(
        default=None,
        description=(
            "Filename sob documents/html/ ou URL /api/files/html/... "
            "de um preview owned pelo usuário (finalize sem reenviar HTML)."
        ),
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "title": "Relatório",
                "blocks": [
                    {"type": "heading", "text": "Resumo", "level": 1},
                    {"type": "paragraph", "text": "Texto."},
                ],
            }
        }
    )

    @model_validator(mode="after")
    def _reject_conflicting_modes(self) -> HtmlDocumentInput:
        has_html = bool(self.html and self.html.strip())
        has_template = bool(self.template and self.template.strip())
        has_preview = bool(self.from_preview and self.from_preview.strip())
        if has_html and has_template:
            raise ValueError(
                "Não combine html e template no mesmo payload; use um ou outro."
            )
        if has_preview and (has_html or has_template or self.blocks):
            raise ValueError(
                "from_preview não pode ser combinado com html, template ou blocks."
            )
        return self
