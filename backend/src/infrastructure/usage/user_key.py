"""Convenção de `user_key` por canal (web / Telegram) e fallbacks."""

from __future__ import annotations

UNKNOWN_USER_KEY = "unknown"


def web_user_key(user_id: str) -> str:
    """Formata a chave de usuário do canal web: `web:<id>`."""
    return f"web:{user_id}"


def telegram_user_key(chat_id: str | int) -> str:
    """Formata a chave de usuário do canal Telegram: `telegram:<chat_id>`."""
    return f"telegram:{chat_id}"


def whatsapp_user_key(phone_number: str) -> str:
    """Formata a chave de usuário do canal WhatsApp: `whatsapp:<phone_number>`."""
    return f"whatsapp:{phone_number}"


def resolve_user_key(
    *,
    user_key: str | None = None,
    owner: str | None = None,
) -> str:
    """Resolve `user_key` com fallbacks: explícito → `web:{owner}` → `unknown`.

    Preferência:
    1. `user_key` já presente no configurable do run
    2. `owner` (LangGraph `metadata.owner` / identity UUID) → `web:<owner>`
    3. Sentinel `unknown` — nunca levanta; o run continua
    """
    if user_key:
        return user_key
    if owner:
        return web_user_key(owner)
    return UNKNOWN_USER_KEY
