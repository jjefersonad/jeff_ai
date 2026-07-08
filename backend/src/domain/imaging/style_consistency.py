"""Domain service de consistência de estilo — a regra "na mesma vibe".

Reaproveita o `DesignStyle` de um design anterior para um novo assunto, mudando
apenas o que o usuário pediu e preservando a identidade visual. Puro: sem
framework, sem I/O.
"""
from __future__ import annotations

from collections.abc import Iterable

from src.domain.imaging.design_style import DesignStyle
from src.domain.imaging.image_design import ImageDesign
from src.domain.imaging.image_reference import ImageReference


def same_vibe(
    previous: ImageDesign,
    new_prompt: str,
    negative_prompt: str | None = None,
    references: Iterable[ImageReference] = (),
) -> ImageDesign:
    """Cria um novo `ImageDesign` reutilizando o estilo de `previous`.

    O assunto passa a ser `new_prompt`; o estilo é mantido. Se `negative_prompt`
    não for informado, herda o do design anterior. `references` (ex.: a imagem
    anterior do thread) condiciona a nova geração para manter a identidade visual.
    """
    return ImageDesign(
        prompt=new_prompt,
        style=previous.style,
        negative_prompt=(
            negative_prompt if negative_prompt is not None else previous.negative_prompt
        ),
        references=tuple(references),
    )


def merge_style(base: DesignStyle, overrides: DesignStyle) -> DesignStyle:
    """Sobrepõe os atributos não nulos de `overrides` sobre `base`.

    Usado para ajustes pontuais de estilo mantendo o restante do design anterior.
    """
    merged = {
        name: (getattr(overrides, name) or getattr(base, name))
        for name in ("art_style", "color_palette", "composition", "dimensions")
    }
    return DesignStyle(**merged)
