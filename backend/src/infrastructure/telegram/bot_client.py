"""Wrapper de cliente da Bot API do Telegram.

Classifica exceções de `python-telegram-bot` em um resultado estruturado
(`success`/`error`/`error_kind`/`retryable`/`retry_after`) para que nenhuma
tool de envio (`src/tools/telegram_tools.py`) precise tratar exceções da
biblioteca diretamente — ver REQ-005 (telegram-tools-spec).
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from telegram.error import BadRequest, Forbidden, RetryAfter, TelegramError

T = TypeVar("T")


def classify_telegram_error(exc: TelegramError) -> dict[str, Any]:
    """Classifica uma exceção de `python-telegram-bot` em erro estruturado.

    Distingue falhas permanentes (`forbidden`, `bad_format`) de transitórias
    (`rate_limited`, `transient`), conforme REQ-005 (telegram-tools-spec).
    """
    if isinstance(exc, RetryAfter):
        return {
            "success": False,
            "error": str(exc),
            "error_kind": "rate_limited",
            "retryable": True,
            "retry_after": exc.retry_after,
        }
    if isinstance(exc, Forbidden):
        return {
            "success": False,
            "error": str(exc),
            "error_kind": "forbidden",
            "retryable": False,
        }
    if isinstance(exc, BadRequest):
        return {
            "success": False,
            "error": str(exc),
            "error_kind": "bad_format",
            "retryable": False,
        }
    return {
        "success": False,
        "error": str(exc),
        "error_kind": "transient",
        "retryable": True,
    }


async def call_bot_api(fn: Callable[[], Awaitable[T]]) -> dict[str, Any]:
    """Executa `fn` (uma chamada assíncrona à Bot API) e nunca levanta.

    Retorna `{"success": True, "result": <retorno de fn>}` em caso de
    sucesso, ou o resultado estruturado de `classify_telegram_error` em caso
    de falha — nenhuma exceção da biblioteca escapa (REQ-005).
    """
    try:
        result = await fn()
    except TelegramError as exc:
        return classify_telegram_error(exc)
    return {"success": True, "result": result}
