"""
ImageDesignInput Pydantic model for structured image generation requests.

Used by the image_design_subagent to plan design parameters
and by create_image_from_prompt tool to receive structured input.
"""
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class ImageDesignInput(BaseModel):
    """
    Schema estruturado para entrada de design de imagem.

    Usado pelo image_design_subagent para planejar parâmetros de design
    e pela tool create_image_from_prompt para receber entrada estruturada.
    """

    prompt: str = Field(
        description="Descrição textual da imagem desejada em linguagem natural."
    )
    art_style: Optional[str] = Field(
        default=None,
        description="Estilo artístico da imagem (ex: 'minimalista', 'futurista', 'pixel art', 'aquarela', 'realista')."
    )
    color_palette: Optional[str] = Field(
        default=None,
        description="Paleta de cores ou tom cromático (ex: 'tons quentes', 'monocromático azul', 'cores vibrantes', 'pastel')."
    )
    composition: Optional[str] = Field(
        default=None,
        description="Composição visual (ex: 'regra dos terços', 'simétrica', 'centralizada', 'diagonal')."
    )
    dimensions: Optional[str] = Field(
        default=None,
        description="Dimensões ou proporções da imagem (ex: '1080x1080', '1920x1080', '1:1', '16:9')."
    )
    negative_prompt: Optional[str] = Field(
        default=None,
        description="Elementos ou características a evitar na imagem (ex: 'sem texto', 'sem logotipos', 'sem elementos realistas demais')."
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "prompt": "Um banner elegante para promoção de serviços de IA para empresas",
                "art_style": "moderno e minimalista",
                "color_palette": "tons de azul e branco",
                "composition": "regra dos terços",
                "dimensions": "1200x628",
                "negative_prompt": "sem texto na imagem"
            }
        }
    )
