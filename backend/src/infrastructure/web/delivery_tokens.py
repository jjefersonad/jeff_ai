"""Token de entrega de uso único para anexos de saída de canais (WhatsApp).

`/api/files/{kind}/{filename}` e `/api/images/{filename}` exigem sessão
autenticada e checam ownership por usuário (`is_authorized`) — corretos para
o frontend, mas inacessíveis a um chamador servidor-a-servidor sem sessão
como a Evolution API, que precisa BUSCAR o attachment via URL para entregá-lo
no WhatsApp (`sendMedia` só aceita `media` como URL, não base64 — verificado
ao vivo, ver `evolution_client.send_media`).

Este módulo mint um token opaco (`secrets.token_urlsafe`) associado a um
arquivo local específico, servido pela rota pública `GET
/public/media-delivery/{token}` (`media_delivery_router.py`) — sob `/public/`,
portanto isento de `require_auth` pelo `PUBLIC_PATHS` default, sem expor o
restante de `/api/files`/`/api/images`. Token é de uso único (removido no
primeiro `resolve_delivery_token` bem-sucedido) e expira em `ttl_seconds` —
o bearer do token é o único controle de acesso necessário, já que mintar só
acontece como consequência direta do próprio usuário dono do anexo (a
confiança já foi estabelecida rio acima, na geração do arquivo).

Estado em memória do processo — mesmo padrão de
`whatsapp/approval.py:_pending_approvals` (um processo backend só).
"""
from __future__ import annotations

import secrets
import time
from typing import TypedDict


class DeliveryTokenPayload(TypedDict):
    """Resolução bem-sucedida de um delivery token — o que a rota de download precisa para servir o arquivo."""
    file_path: str
    filename: str
    mime: str


class _TokenEntry(TypedDict):
    file_path: str
    filename: str
    mime: str
    expires_at: float


_tokens: dict[str, _TokenEntry] = {}


def mint_delivery_token(
    file_path: str, filename: str, mime: str, ttl_seconds: int = 600
) -> str:
    """Gera um token opaco de uso único para `file_path`, válido por `ttl_seconds`."""
    token = secrets.token_urlsafe(32)
    _tokens[token] = {
        "file_path": file_path,
        "filename": filename,
        "mime": mime,
        "expires_at": time.monotonic() + ttl_seconds,
    }
    return token


def resolve_delivery_token(token: str) -> DeliveryTokenPayload | None:
    """Resolve e consome `token` — `None` se ausente ou expirado.

    Uso único: uma resolução bem-sucedida remove o token do dicionário.
    """
    entry = _tokens.get(token)
    if entry is None:
        return None
    if entry["expires_at"] < time.monotonic():
        del _tokens[token]
        return None
    del _tokens[token]
    return {
        "file_path": entry["file_path"],
        "filename": entry["filename"],
        "mime": entry["mime"],
    }
