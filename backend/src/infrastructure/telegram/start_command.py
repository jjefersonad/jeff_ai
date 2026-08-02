"""Comando `/start <code>` do canal Telegram (vínculo de conta).

Responsabilidade desta task (`user-integration-credentials-task-linking-2`):

- Parsear `/start <code>` e chamar `RedeemTelegramLinkCode.execute(code, chat_id)`
  (`user-integration-credentials-task-linking-1`).
- Responder ao chat com uma confirmação legível em caso de sucesso, ou um
  erro legível (sem detalhe interno) quando o código é inexistente, expirado
  ou já usado (`TelegramLinkCodeInvalidError`) — mesmo erro para os três
  casos, REQ-002 cenários 2/3 do spec `telegram-account-linking`.

Diferente de `commands.py`, este handler NÃO aplica `is_authorized_chat`: o
próprio propósito do `/start` é vincular um `chat_id` ainda não autorizado a
um `user_id` — exigir autorização prévia tornaria o vínculo impossível.

Fronteira do handler: nenhuma exceção escapa (mesma garantia de
`authorization.py`/`commands.py`) — o loop de polling do
`python-telegram-bot` precisa continuar vivo mesmo quando a redenção falha.
"""
from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Protocol

from src.application.use_cases.redeem_telegram_link_code import (
    TelegramLinkCodeInvalidError,
)
from src.infrastructure.telegram import bot_client

logger = logging.getLogger(__name__)

_USAGE_MESSAGE = "Uso: /start <código>"
_SUCCESS_MESSAGE = "Conta vinculada com sucesso! Você já pode usar o bot."
_INVALID_CODE_MESSAGE = "Código de vínculo inválido, expirado ou já utilizado."
_GENERIC_ERROR_MESSAGE = (
    "Ocorreu uma falha ao processar seu código. Tente novamente em alguns instantes."
)


class _RedeemLinkCodePort(Protocol):
    """Tipo estrutural mínimo: só o `execute(code, chat_id)` usado aqui."""

    async def execute(self, *, code: str, chat_id: str) -> Any: ...


class _BotLike(Protocol):
    """Duck type mínimo: só `send_message`, igual ao de `authorization.py`."""

    async def send_message(
        self, chat_id: Any, text: str, *args: Any, **kwargs: Any
    ) -> Any: ...


def _parse_code(text: str) -> str:
    """Extrai o código de `/start <code>`, ou string vazia se ausente.

    "/start ABC123" -> "ABC123"; "/start" ou "/start   " -> "".
    """
    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        return ""
    return parts[1].strip()


async def _send(bot: _BotLike, chat_id: str, text: str) -> None:
    """Responde ao chat via a mesma fronteira tipada de `authorization.py`."""
    await bot_client.call_bot_api(lambda: bot.send_message(chat_id=chat_id, text=text))


def make_start_command_handler(
    *,
    redeem_use_case: _RedeemLinkCodePort,
    bot: _BotLike,
) -> Callable[[Any, Any], Awaitable[None]]:
    """Constrói o callback compatível com `Application.add_handler(CommandHandler(["start"], ...))`."""

    async def handler(update: Any, context: Any) -> None:
        chat_id = str(update.effective_chat.id) if update.effective_chat else ""
        text = getattr(update.message, "text", "") or ""
        code = _parse_code(text)
        if not code:
            await _send(bot, chat_id, _USAGE_MESSAGE)
            return

        try:
            await redeem_use_case.execute(code=code, chat_id=chat_id)
        except TelegramLinkCodeInvalidError:
            await _send(bot, chat_id, _INVALID_CODE_MESSAGE)
            return
        except Exception:  # noqa: BLE001 — fronteira do handler
            logger.exception(
                "Falha inesperada ao redimir código de vínculo para chat_id=%s.",
                chat_id,
            )
            await _send(bot, chat_id, _GENERIC_ERROR_MESSAGE)
            return

        await _send(bot, chat_id, _SUCCESS_MESSAGE)

    return handler
