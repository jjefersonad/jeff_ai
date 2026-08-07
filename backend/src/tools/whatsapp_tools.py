"""Tool de envio ativo para o canal WhatsApp (Evolution API, número central).

Task `whatsapp-evolution-channel-task-tools-2`: diferente de
`send_telegram_message` (destino padrão single-user via env var), o número
central WhatsApp (Modelo B, ver design do change) atende vários usuários
vinculados simultaneamente — por isso, quando `phone_number` não é
informado, o destino é resolvido a partir do vínculo WhatsApp
(`user_integrations`) do `user_id` da sessão atual, via `resolve_user_id()`
(mesmo resolvedor canônico usado por `ownership/store.py`).

`send_whatsapp_message` é wrapper deprecated (cleanup-1): permanece
importável para skills/scripts externos, mas não está em `_UNIFIED_TOOLS`.
Delega a `ChannelRegistry` → `WhatsAppChannel.deliver`.
"""
from __future__ import annotations

import logging
import os
from typing import Any

from langchain_core.tools import tool

from src.domain.channels import ChannelKind
from src.infrastructure.channels.registry import ChannelRegistry
from src.infrastructure.ownership.store import resolve_user_id
from src.infrastructure.persistence.user_integrations_repository import (
    PostgresUserIntegrationRepository,
)
from src.infrastructure.usage.user_key import whatsapp_user_key

logger = logging.getLogger(__name__)

_WHATSAPP_INTEGRATION_TYPE = "whatsapp_business"

_NO_LINK_RESULT: dict[str, Any] = {
    "success": False,
    "error": "Sessão atual não tem número WhatsApp vinculado.",
    "error_kind": "not_linked",
    "retryable": False,
}


async def _resolve_linked_phone_number() -> str | None:
    """`phone_number` vinculado ao `user_id` da sessão atual, ou `None` sem vínculo."""
    user_id = await resolve_user_id()
    if user_id is None:
        return None

    repository = PostgresUserIntegrationRepository(os.environ["POSTGRES_URI"])
    for integration in await repository.list_by_user(user_id):
        if integration.integration_type != _WHATSAPP_INTEGRATION_TYPE:
            continue
        phone_number = integration.config.get("phone_number")
        if isinstance(phone_number, str) and phone_number:
            return phone_number
    return None


@tool
async def send_whatsapp_message(text: str, phone_number: str | None = None) -> dict[str, Any]:
    """Envia uma mensagem de texto a um contato WhatsApp via Evolution API.

    .. deprecated::
        Use `send_message` (canal-agnóstica) ou o pipeline
        `HandleChatMessage`. Este wrapper permanece por uma release para
        skills/scripts que ainda importam a tool diretamente.

    Quando `phone_number` não é informado, resolve o destino a partir do
    vínculo WhatsApp da sessão atual em `user_integrations`. Sem destino
    explícito e sem vínculo ativo, retorna erro sem chamar o registry.
    Delega a `WhatsAppChannel.deliver` via `ChannelRegistry`.
    """
    logger.warning(
        "send_whatsapp_message is deprecated; use send_message. "
        "Will be removed after callers migrate to HandleChatMessage."
    )
    target_phone_number = phone_number
    if target_phone_number is None:
        target_phone_number = await _resolve_linked_phone_number()
        if target_phone_number is None:
            return _NO_LINK_RESULT

    channel = ChannelRegistry.get(ChannelKind.WHATSAPP)
    await channel.deliver(
        user_key=whatsapp_user_key(target_phone_number),
        text=text,
        attachments=(),
        kind="normal",
    )
    return {"success": True}
