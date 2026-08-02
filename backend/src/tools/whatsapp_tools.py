"""Tool de envio ativo para o canal WhatsApp (Evolution API, número central).

Task `whatsapp-evolution-channel-task-tools-2`: diferente de
`send_telegram_message` (destino padrão single-user via env var), o número
central WhatsApp (Modelo B, ver design do change) atende vários usuários
vinculados simultaneamente — por isso, quando `phone_number` não é
informado, o destino é resolvido a partir do vínculo WhatsApp
(`user_integrations`) do `user_id` da sessão atual, via `resolve_user_id()`
(mesmo resolvedor canônico usado por `ownership/store.py`).
"""
from __future__ import annotations

import os
from typing import Any

import httpx
from langchain_core.tools import tool

from src.infrastructure.ownership.store import resolve_user_id
from src.infrastructure.persistence.user_integrations_repository import (
    PostgresUserIntegrationRepository,
)
from src.infrastructure.whatsapp import evolution_client

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

    Quando `phone_number` não é informado, resolve o destino a partir do
    vínculo WhatsApp da sessão atual em `user_integrations`. Sem destino
    explícito e sem vínculo ativo, retorna erro sem chamar a Evolution API.
    Falhas da Evolution API (janela de 24h expirada, rate limit, etc.) são
    classificadas por `evolution_client.classify_send_error` em vez de
    propagar a exceção (REQ-003, whatsapp-tools-spec).
    """
    target_phone_number = phone_number
    if target_phone_number is None:
        target_phone_number = await _resolve_linked_phone_number()
        if target_phone_number is None:
            return _NO_LINK_RESULT

    config = evolution_client.bootstrap_config()
    try:
        await evolution_client.send_text(config.instance_name, target_phone_number, text)
    except httpx.HTTPStatusError as exc:
        return evolution_client.classify_send_error(exc)
    return {"success": True}
