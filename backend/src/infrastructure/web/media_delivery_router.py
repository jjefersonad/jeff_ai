"""Rota pública de entrega de anexos por token de uso único (WhatsApp).

`GET /public/media-delivery/{token}` — sob `/public/`, isenta de
`require_auth` pelo `PUBLIC_PATHS` default (`session_resolver.py`). Existe
para que a Evolution API (chamador servidor-a-servidor, sem sessão) consiga
buscar o arquivo de um attachment via `sendMedia`'s `media` (que só aceita
URL, não base64 — ver `evolution_client.send_media`), sem expor
`/api/files`/`/api/images` (autenticadas, com ownership por usuário).

Ver `delivery_tokens.py` para o mint/resolve do token.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from src.infrastructure.web.delivery_tokens import resolve_delivery_token

router = APIRouter()


@router.get("/public/media-delivery/{token}")
async def serve_media_delivery(token: str):
    payload = resolve_delivery_token(token)
    if payload is None:
        raise HTTPException(status_code=404, detail="Token not found or expired")

    return FileResponse(
        path=payload["file_path"],
        media_type=payload["mime"],
        headers={"Content-Disposition": f'attachment; filename="{payload["filename"]}"'},
    )
