"""Tool de entrega explícita: `send_message`.

Resolve o canal via `configurable.user_key` → `ChannelRegistry` e delega a
`ChatChannelPort.deliver` (design `unify-message-delivery-pipeline`).
Registrada em `_UNIFIED_TOOLS` no lugar de `send_telegram_message` /
`send_whatsapp_message` (que ficam como wrappers deprecated — task
cleanup-1).
"""
from __future__ import annotations

import mimetypes
import os
from pathlib import Path
from typing import Any

from langchain_core.tools import tool
from langgraph.config import get_config

from src.domain.channels import OutputAttachment
from src.infrastructure.channels.registry import ChannelRegistry
from src.infrastructure.usage.user_key import from_user_key


def _current_user_key() -> str | None:
    return get_config().get("configurable", {}).get("user_key")


def _resolve_attachments(attachment_paths: list[str] | tuple[str, ...]) -> tuple[OutputAttachment, ...]:
    """Converte paths em `OutputAttachment` (mime/display_name via extensão)."""
    attachments: list[OutputAttachment] = []
    for path in attachment_paths:
        mime, _ = mimetypes.guess_type(path)
        attachments.append(
            OutputAttachment(
                path=path,
                mime=mime or "application/octet-stream",
                display_name=os.path.basename(path) or Path(path).name,
            )
        )
    return tuple(attachments)


@tool
async def send_message(
    text: str,
    attachment_paths: list[str] | None = None,
) -> dict[str, Any]:
    """Envia uma mensagem ao usuário do canal corrente.

    Resolve o canal a partir de `configurable.user_key` e entrega via
    `ChannelRegistry`. Use para confirmar/anexar conteúdo fora da captura
    automática do turno; respostas de texto puro já são entregues sem
    chamar esta tool.
    """
    user_key = _current_user_key()
    kind = from_user_key(user_key)
    if user_key is None or kind is None:
        raise RuntimeError(
            "send_message exige configurable.user_key com prefixo de canal "
            f"reconhecido; recebido: {user_key!r}"
        )

    channel = ChannelRegistry.get(kind)
    await channel.deliver(
        user_key=user_key,
        text=text,
        attachments=_resolve_attachments(attachment_paths or ()),
        kind="normal",
    )
    return {"success": True}
