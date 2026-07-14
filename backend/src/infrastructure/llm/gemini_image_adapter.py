"""Adapter de geração de imagem via Google Gemini (implementa `ImageGenPort`)."""
from __future__ import annotations

import asyncio
import datetime
import json
import os
from pathlib import Path
from typing import Any

from google import genai
from google.genai import types

from src.application.ports.image_gen import GeneratedImage, ImageGenPort
from src.domain.imaging import ImageDesign
from src.infrastructure.media.image_signatures import sniff_image_mime

# backend/outputs/images (mesmo destino do comportamento legado).
_DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parents[3] / "outputs" / "images"
_DEFAULT_MODEL = "gemini-3.1-flash-image"


class GeminiImageAdapter(ImageGenPort):
    """Gera imagens com a API Gemini e persiste PNG + sidecar JSON de metadados.

    Converte a resposta crua do SDK em `GeneratedImage` (tipo de aplicação),
    sem vazar objetos do SDK para as camadas internas.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        output_dir: Path | None = None,
        url_prefix: str = "/api/images",
        model: str = _DEFAULT_MODEL,
    ) -> None:
        """Configura o cliente Gemini e o destino das imagens (secrets ficam aqui)."""
        self._client = genai.Client(api_key=api_key or os.getenv("GOOGLE_API_KEY"))
        self._output_dir = output_dir or _DEFAULT_OUTPUT_DIR
        self._url_prefix = url_prefix.rstrip("/")
        self._model = model

    async def generate(self, design: ImageDesign) -> GeneratedImage:
        """Gera a imagem do `design`, envolvendo a chamada síncrona do SDK em thread."""
        return await asyncio.to_thread(self._generate_sync, design)

    def _generate_sync(self, design: ImageDesign) -> GeneratedImage:
        # Carrega as referências ANTES de chamar a API: se alguma for ilegível,
        # aborta sem gerar (REQ-006). Sem referências, envia só o prompt (REQ-001).
        contents = self._build_contents(design)
        response = self._client.models.generate_content(
            model=self._model,
            contents=contents,
        )
        for part in response.parts:
            if part.inline_data is None:
                continue
            image = part.as_image()
            image_name = self._timestamp() + ".png"
            self._output_dir.mkdir(parents=True, exist_ok=True)
            image_path = self._output_dir / image_name
            image.save(image_path)

            metadata = design.metadata()
            sidecar_path = self._output_dir / image_name.replace(".png", "_metadata.json")
            with open(sidecar_path, "w", encoding="utf-8") as sidecar:
                json.dump(metadata, sidecar, ensure_ascii=False, indent=2)

            return GeneratedImage(
                path=str(image_path),
                url=f"{self._url_prefix}/{image_name}",
                metadata=metadata,
            )

        raise RuntimeError("A API Gemini não retornou nenhuma imagem na resposta.")

    def _build_contents(self, design: ImageDesign) -> list[Any]:
        """Monta o `contents` da chamada: imagens de referência ANTES do prompt.

        Sem referências, retorna `[prompt]` (comportamento text-only). Com
        referências, carrega cada imagem do filesystem (só a infra conhece o SDK)
        e retorna `[*parts, prompt]`. Caminho inexistente/ilegível levanta erro
        claro antes de qualquer chamada à API (nenhuma imagem é gerada).
        """
        parts = [self._load_reference(ref.path) for ref in design.references]
        return [*parts, design.prompt]

    @staticmethod
    def _load_reference(path: str) -> types.Part:
        """Lê e valida uma imagem de referência como `types.Part` (REQ-006).

        Erro claro se o arquivo não existir, não puder ser lido, ou não for uma
        imagem em formato suportado — sempre ANTES de chamar a API.
        """
        try:
            data = Path(path).read_bytes()
        except OSError as exc:
            raise RuntimeError(
                f"Imagem de referência ilegível ou inexistente: {path!r} ({exc})."
            ) from exc

        mime_type = sniff_image_mime(data)
        if mime_type is None:
            raise RuntimeError(
                f"Imagem de referência em formato não suportado: {path!r}."
            )
        return types.Part.from_bytes(data=data, mime_type=mime_type)

    @staticmethod
    def _timestamp() -> str:
        return datetime.datetime.now().strftime("%Y%m%d%H%M%S")
