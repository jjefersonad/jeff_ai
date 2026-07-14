"""Tool `create_image_from_prompt` — adapter fino sobre o caso de uso PlanAndCreateImage.

Esta tool é apenas a borda deepagents: traduz a entrada (string ou
`ImageDesignInput`) para o domínio, injeta os adapters de infraestrutura e
delega a geração ao caso de uso. NÃO contém regra de negócio.
"""
from __future__ import annotations

from typing import Union

from langchain_core.tools import tool

from src.composition.dependencies import build_plan_and_create_image
from src.domain.imaging import DesignStyle, ImageDesign, ImageReference
from src.domain.shared.errors import DomainError
from src.models.image_design import ImageDesignInput


def _clean(value: str | None) -> str | None:
    """Normaliza strings de entrada: vazio/whitespace vira None."""
    return value.strip() if isinstance(value, str) and value.strip() else None


def _to_image_design(design_input: Union[str, ImageDesignInput]) -> ImageDesign:
    """Constrói o `ImageDesign` a partir da entrada da tool (string ou ImageDesignInput).

    Mantém o contrato tolerante da tool: campos vazios viram None e dimensões em
    formato livre (não `WxH`/`W:H`) são descartadas para não bloquear a geração.
    """
    if isinstance(design_input, str):
        return ImageDesign(prompt=design_input)

    common = {
        "art_style": _clean(design_input.art_style),
        "color_palette": _clean(design_input.color_palette),
        "composition": _clean(design_input.composition),
    }
    try:
        style = DesignStyle(**common, dimensions=_clean(design_input.dimensions))
    except DomainError:
        # Dimensões em formato livre: preserva a geração, descartando só esse campo.
        style = DesignStyle(**common)

    return ImageDesign(
        prompt=design_input.prompt,
        style=style,
        negative_prompt=_clean(design_input.negative_prompt),
        references=_to_references(design_input.references),
    )


def _to_references(paths: list[str] | None) -> tuple[ImageReference, ...]:
    """Converte caminhos livres em `ImageReference`, ignorando entradas vazias."""
    if not paths:
        return ()
    return tuple(ImageReference(path=cleaned) for p in paths if (cleaned := _clean(p)))


@tool
async def create_image_from_prompt(
    design_input: Union[str, ImageDesignInput]
) -> dict:
    """Generate an image from a prompt (or ImageDesignInput) via the Google Gemini API.

    Saves the image and a sidecar JSON with design metadata. Accepts either a plain
    prompt string (legacy mode) or an ImageDesignInput with optional design params
    (art_style, color_palette, composition, dimensions, negative_prompt).

    Returns a dict with:
    - path: local filesystem path (internal use only, do NOT show to the user).
    - url: frontend-accessible URL — ALWAYS use this in markdown to display the image.
    - metadata: the design metadata used for generation.

    Example return:
    {"path": "/app/backend/outputs/images/20260705091430.png",
     "url": "/api/images/20260705091430.png",
     "metadata": {"prompt": "Um gato astronauta no espaço", "art_style": "realista",
                  "color_palette": "tons frios", "composition": "centralizada",
                  "dimensions": "1024x1024", "negative_prompt": null}}
    """
    design = _to_image_design(design_input)

    use_case = build_plan_and_create_image()
    result = await use_case.execute(design)

    return {"path": result.path, "url": result.url, "metadata": result.metadata}
