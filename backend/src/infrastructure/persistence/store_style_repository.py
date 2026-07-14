"""Adapter de repositório de estilos sobre o Store do LangGraph (`StyleRepositoryPort`)."""
from __future__ import annotations

import datetime
import uuid
from typing import Any

from src.application.ports.style_repository import StyleRepositoryPort
from src.domain.imaging import DesignStyle, ImageDesign

_STYLES_ROOT = "styles"


class StoreStyleRepository(StyleRepositoryPort):
    """Persiste `ImageDesign` aprovados no namespace `("styles", thread_id)` do Store.

    Guarda o design de forma estruturada (chave `design`), tolerando itens legados
    (sem essa chave) gravados por outras ferramentas no mesmo namespace.
    """

    def __init__(self, store: Any) -> None:
        """Recebe o Store do LangGraph (Postgres/pgvector) por injeção."""
        self._store = store

    async def save(
        self, thread_id: str, design: ImageDesign, image_path: str | None = None
    ) -> None:
        """Salva `design` como uma nova versão (nunca sobrescreve).

        Se `image_path` for informado, persiste o caminho da imagem gerada para
        reuso posterior como referência visual.
        """
        created_at = datetime.datetime.now(datetime.UTC).isoformat()
        key = f"{created_at}-{uuid.uuid4().hex[:8]}"
        value: dict[str, Any] = {"design": design.metadata(), "created_at": created_at}
        if image_path:
            value["image_path"] = image_path
        await self._store.aput((_STYLES_ROOT, thread_id), key, value)

    async def latest(self, thread_id: str) -> ImageDesign | None:
        """Retorna o `ImageDesign` estruturado mais recente do thread, ou None."""
        items = await self._store.asearch((_STYLES_ROOT, thread_id), limit=100)
        structured = [
            it
            for it in items
            if isinstance(it.value.get("design"), dict)
            and (it.value["design"].get("prompt") or "").strip()
        ]
        if not structured:
            return None
        newest = max(structured, key=lambda it: it.value.get("created_at", ""))
        return self._from_dict(newest.value["design"])

    async def latest_image_path(self, thread_id: str) -> str | None:
        """Retorna o `image_path` do registro mais recente que o tenha, ou None."""
        items = await self._store.asearch((_STYLES_ROOT, thread_id), limit=100)
        with_path = [
            it
            for it in items
            if isinstance(it.value, dict) and (it.value.get("image_path") or "").strip()
        ]
        if not with_path:
            return None
        newest = max(with_path, key=lambda it: it.value.get("created_at", ""))
        return newest.value["image_path"]

    @staticmethod
    def _from_dict(data: dict[str, Any]) -> ImageDesign:
        style = DesignStyle(
            art_style=data.get("art_style"),
            color_palette=data.get("color_palette"),
            composition=data.get("composition"),
            dimensions=data.get("dimensions"),
        )
        return ImageDesign(
            prompt=data["prompt"],
            style=style,
            negative_prompt=data.get("negative_prompt"),
        )
