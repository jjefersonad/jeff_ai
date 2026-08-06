"""`TelegramChannel` — adapter `ChatChannelPort` para o canal Telegram.

Encapsula TODO o protocolo de saída Telegram: texto (`bot.send_message`),
mídia (`bot.send_photo`/`bot.send_document`) e o teclado de aprovação
(`approval.send_approval_keyboard`) para `kind="interruption"`. Delega toda
chamada à Bot API via `bot_client.call_bot_api` — a mesma rota usada por
`tools/telegram_tools.py` e `approval.py` — para nunca deixar uma exceção
de `python-telegram-bot` (rate limit, timeout, etc.) escapar (REQ-005
chat-channel-port, REQ-011 telegram-channel).

Typing (typing-indicator-chat-channels Decision 5): `send_chat_action(typing)`
com refresh ~4s; `stop` cancela a task — falhas engolidas.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
from pathlib import Path

from src.application.ports.agent_runner import InterruptInfo
from src.application.ports.chat_channel import ChatChannelPort, DeliveryKind
from src.domain.channels import ChannelKind, OutputAttachment
from src.infrastructure.telegram import approval, bot_client

logger = logging.getLogger(__name__)

# Mensagem amigável quando `kind="failure"` chega sem `text` (DeliveryKind /
# chat-channel-port REQ-001: `"failure"` substitui por mensagem do canal).
# Mesmo texto que o antigo `_CHANNEL_ERROR_MESSAGE` de `authorization.py`.
_FAILURE_MESSAGE = (
    "Ocorreu uma falha ao processar sua mensagem. "
    "Tente novamente em alguns instantes."
)

# Bot API expira chat action ~5s — refresh um pouco antes (design Decision 5).
_TYPING_REFRESH_SECONDS = 4.0


def _chat_id(user_key: str) -> int:
    """Extrai o `chat_id` numérico do prefixo `"telegram:<chat_id>"`."""
    return int(user_key.removeprefix("telegram:"))


class TelegramChannel(ChatChannelPort):
    """Adapter Telegram — construtor recebe o `Bot` do `python-telegram-bot` por injeção."""

    def __init__(self, *, bot: object) -> None:
        """Guarda o `Bot` (injetado) usado em toda chamada à Bot API."""
        self._bot = bot
        self._typing_tasks: dict[str, asyncio.Task[None]] = {}

    @property
    def channel_kind(self) -> ChannelKind:
        """Sempre `ChannelKind.TELEGRAM` — usado por `ChannelRegistry.register`."""
        return ChannelKind.TELEGRAM

    async def deliver(
        self,
        *,
        user_key: str,
        text: str | None,
        attachments: tuple[OutputAttachment, ...],
        kind: DeliveryKind,
        interrupt: InterruptInfo | None = None,
        thread_id: str | None = None,
    ) -> None:
        """Entrega via Bot API — texto simples, mídia com caption, ou teclado de aprovação."""
        chat_id = _chat_id(user_key)

        if kind == "interruption":
            await approval.send_approval_keyboard(
                bot=self._bot,
                chat_id=str(chat_id),
                thread_id=thread_id or "",
                interrupt=interrupt,
            )
            return

        if kind == "failure":
            await self._send_text(chat_id, text or _FAILURE_MESSAGE)
            return

        if not attachments:
            await self._send_text(chat_id, text)
            return

        # Texto vem junto com o primeiro anexo (caption) — nunca como
        # mensagem separada (REQ-011: "não separado em 2 mensagens").
        for index, attachment in enumerate(attachments):
            caption = text if index == 0 else None
            await self._send_attachment(chat_id, attachment, caption=caption)

    async def _send_text(self, chat_id: int, text: str | None) -> None:
        try:
            result = await bot_client.call_bot_api(
                lambda: self._bot.send_message(chat_id=chat_id, text=text)  # type: ignore[attr-defined]
            )
        except Exception:  # noqa: BLE001 — REQ-005: deliver nunca propaga
            logger.warning(
                "TelegramChannel.deliver falhou: chat_id=%s error_kind=unexpected",
                chat_id,
                exc_info=True,
            )
            return
        self._log_if_failed(result, chat_id=chat_id)

    async def _send_attachment(
        self, chat_id: int, attachment: OutputAttachment, *, caption: str | None
    ) -> None:
        try:
            content = Path(attachment.path).read_bytes()
            if attachment.mime.startswith("image/"):
                result = await bot_client.call_bot_api(
                    lambda: self._bot.send_photo(  # type: ignore[attr-defined]
                        chat_id=chat_id, photo=content, caption=caption
                    )
                )
            else:
                result = await bot_client.call_bot_api(
                    lambda: self._bot.send_document(  # type: ignore[attr-defined]
                        chat_id=chat_id, document=content, caption=caption
                    )
                )
        except Exception:  # noqa: BLE001 — REQ-005: deliver nunca propaga
            logger.warning(
                "TelegramChannel.deliver falhou: chat_id=%s error_kind=unexpected",
                chat_id,
                exc_info=True,
            )
            return
        self._log_if_failed(result, chat_id=chat_id)

    def _log_if_failed(self, result: dict, *, chat_id: int) -> None:
        if result["success"]:
            return
        logger.warning(
            "TelegramChannel.deliver falhou: chat_id=%s error_kind=%s",
            chat_id,
            result.get("error_kind"),
        )

    async def start_typing_indicator(self, *, user_key: str) -> None:
        """Envia `typing` via Bot API e mantém refresh até `stop` (Decision 5)."""
        try:
            chat_id = _chat_id(user_key)
        except (TypeError, ValueError):
            logger.warning(
                "TelegramChannel.start_typing_indicator: user_key inválido=%r",
                user_key,
            )
            return

        await self._cancel_typing(user_key)
        await self._send_typing_action(chat_id)
        self._typing_tasks[user_key] = asyncio.create_task(
            self._typing_refresh_loop(chat_id),
            name=f"telegram-typing:{user_key}",
        )

    async def stop_typing_indicator(self, *, user_key: str) -> None:
        """Cancela o refresh de typing para `user_key` (idempotente)."""
        await self._cancel_typing(user_key)

    async def _cancel_typing(self, user_key: str) -> None:
        task = self._typing_tasks.pop(user_key, None)
        if task is None:
            return
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    async def _send_typing_action(self, chat_id: int) -> None:
        try:
            result = await bot_client.call_bot_api(
                lambda: self._bot.send_chat_action(  # type: ignore[attr-defined]
                    chat_id=chat_id, action="typing"
                )
            )
        except Exception:  # noqa: BLE001 — typing é best-effort
            logger.warning(
                "TelegramChannel.typing falhou: chat_id=%s error_kind=unexpected",
                chat_id,
                exc_info=True,
            )
            return
        if not result.get("success", False):
            logger.warning(
                "TelegramChannel.typing falhou: chat_id=%s error_kind=%s",
                chat_id,
                result.get("error_kind"),
            )

    async def _typing_refresh_loop(self, chat_id: int) -> None:
        try:
            while True:
                await asyncio.sleep(_TYPING_REFRESH_SECONDS)
                await self._send_typing_action(chat_id)
        except asyncio.CancelledError:
            raise


__all__ = ["TelegramChannel"]
