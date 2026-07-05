import os
import datetime
import json
from dotenv import load_dotenv
from google import genai
from langchain_core.tools import tool
from pathlib import Path
from typing import Union

from src.models.image_design import ImageDesignInput

SPECIFY_DIR = Path(__file__).parent.parent.parent / "outputs" / "images"

load_dotenv()

api_key = os.getenv("GOOGLE_API_KEY")
client = genai.Client(api_key=api_key)


def create_hash_timestamp():
    now = datetime.datetime.now()
    return now.strftime("%Y%m%d%H%M%S")


def _normalize_design_input(design_input: Union[str, ImageDesignInput]) -> ImageDesignInput:
    """Converte entrada string para ImageDesignInput (retrocompatibilidade)."""
    if isinstance(design_input, str):
        return ImageDesignInput(prompt=design_input)
    return design_input


@tool
def create_image_from_prompt(
    design_input: Union[str, ImageDesignInput]
) -> dict:
    """
    Generates an image from a text prompt or structured design input using the Google Gemini API,
    saving the image and a sidecar JSON with design metadata.

    Accepts either a plain prompt string (legacy mode) or an ImageDesignInput object
    for structured, planned image generation with design metadata.

    Args:
        design_input: Either a plain prompt string or an ImageDesignInput object containing
            the prompt and optional design parameters (art_style, color_palette,
            composition, dimensions, negative_prompt).

    Returns:
        dict: A dictionary containing:
            - path: The local filesystem path (internal use only, do NOT show to user).
            - url: The frontend-accessible URL that should be used in markdown messages.
            - metadata: Design metadata including the design plan used for generation.
              Example return:
              {
                  "path": "/app/backend/outputs/images/20260705091430.png",
                  "url": "/api/images/20260705091430.png",
                  "metadata": {
                      "prompt": "Um gato astronauta no espaço",
                      "art_style": "realista",
                      "color_palette": "tons frios",
                      "composition": "centralizada",
                      "dimensions": "1024x1024",
                      "negative_prompt": None
                  }
              }
              IMPORTANT: Always use the "url" field when writing markdown to display the image to the user.
    """
    # Normaliza entrada: se for string, converte para ImageDesignInput
    design = _normalize_design_input(design_input)

    # Extrai o prompt para envio à API Gemini
    prompt_text = design.prompt

    # Envia para a Gemini API
    response = client.models.generate_content(
        model="gemini-3.1-flash-image",
        contents=[prompt_text],
    )

    for part in response.parts:
        if part.inline_data is not None:
            image = part.as_image()
            image_name = create_hash_timestamp() + ".png"
            image_path = SPECIFY_DIR / image_name
            os.makedirs(SPECIFY_DIR, exist_ok=True)
            image.save(image_path)

            # Salva sidecar JSON com metadados de design
            metadata = {
                "prompt": design.prompt,
                "art_style": design.art_style,
                "color_palette": design.color_palette,
                "composition": design.composition,
                "dimensions": design.dimensions,
                "negative_prompt": design.negative_prompt,
            }
            sidecar_path = SPECIFY_DIR / (image_name.replace(".png", "_metadata.json"))
            with open(sidecar_path, "w", encoding="utf-8") as f:
                json.dump(metadata, f, ensure_ascii=False, indent=2)

            return {
                "path": str(image_path),
                "url": f"/api/images/{image_name}",
                "metadata": metadata,
            }
