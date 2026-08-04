"""`WhatsAppChannel` — adapter `ChatChannelPort` para o canal WhatsApp (Evolution API).

Encapsula o protocolo de saída Evolution API: texto (`evolution_client.send_text`,
com chunking para textos > 4096 chars), imagem (`evolution_client.send_image`)
e a mensagem de fallback de aprovação para `kind="interruption"` — a Evolution
API/WhatsApp não suporta botões inline (REQ-008 whatsapp-channel).

`send_text`/`send_image` propagam `httpx.HTTPError` (não engolem, ao
contrário do `bot_client` do Telegram) — este adapter é quem chama
`evolution_client.classify_send_error` e engole, mantendo o mesmo contrato
fail-safe do `ChatChannelPort` (REQ-005 chat-channel-port).
"""
from __future__ import annotations

import base64
import logging
from pathlib import Path

import httpx

from src.application.ports.agent_runner import InterruptInfo
from src.application.ports.chat_channel import ChatChannelPort, DeliveryKind
from src.domain.channels import ChannelKind, OutputAttachment
from src.infrastructure.whatsapp import evolution_client

logger = logging.getLogger(__name__)

_TEXT_CHUNK_LIMIT = 4096
"""Limite de caracteres por mensagem de texto na Evolution API / WhatsApp."""

_APPROVAL_PENDING_MESSAGE = (
    "Uma ação requer aprovação. Abra o Jeff AI pelo Telegram ou web para revisar."
)

# Mensagem amigável quando `kind="failure"` chega sem `text` (DeliveryKind /
# chat-channel-port REQ-001). Mesmo texto do antigo `_CHANNEL_ERROR_MESSAGE`
# do webhook WhatsApp.
_FAILURE_MESSAGE = (
    "Ocorreu uma falha ao processar sua mensagem. "
    "Tente novamente em alguns instantes."
)


def _split_into_chunks(text: str, limit: int = _TEXT_CHUNK_LIMIT) -> list[str]:
    """Divide `text` em pedaços de até `limit` caracteres, preservando a ordem."""
    if len(text) <= limit:
        return [text]
    return [text[i : i + limit] for i in range(0, len(text), limit)]


def _phone(user_key: str) -> str:
    """Extrai o número de telefone do prefixo `"whatsapp:<phone>"`."""
    return user_key.removeprefix("whatsapp:")


class WhatsAppChannel(ChatChannelPort):
    """Adapter WhatsApp — construtor recebe o nome da `instance` da Evolution API."""

    def __init__(self, *, instance: str) -> None:
        """Guarda `instance` (usado em toda chamada a `evolution_client`)."""
        self._instance = instance

    @property
    def channel_kind(self) -> ChannelKind:
        """Sempre `ChannelKind.WHATSAPP` — usado por `ChannelRegistry.register`."""
        return ChannelKind.WHATSAPP

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
        """Entrega via Evolution API — texto (com chunking), imagem com caption, ou fallback de aprovação."""
        phone = _phone(user_key)

        if kind == "interruption":
            await self._send_text_safe(phone, _APPROVAL_PENDING_MESSAGE)
            return

        if kind == "failure":
            await self._send_text_safe(phone, text or _FAILURE_MESSAGE)
            return

        if attachments:
            await self._send_attachment_safe(phone, attachments[0], caption=text)
            return

        if text:
            for chunk in _split_into_chunks(text):
                await self._send_text_safe(phone, chunk)

    async def _send_text_safe(self, phone: str, text: str) -> None:
        try:
            await evolution_client.send_text(self._instance, phone, text)
        except Exception as exc:  # noqa: BLE001 — REQ-005: deliver nunca propaga
            if isinstance(exc, httpx.HTTPStatusError):
                self._log_failure(phone, evolution_client.classify_send_error(exc))
            else:
                logger.warning(
                    "WhatsAppChannel.deliver falhou: phone=%s error_kind=unexpected",
                    phone,
                    exc_info=True,
                )

    async def _send_attachment_safe(
        self, phone: str, attachment: OutputAttachment, *, caption: str | None
    ) -> None:
        media_base64 = base64.b64encode(Path(attachment.path).read_bytes()).decode()
        try:
            await evolution_client.send_image(self._instance, phone, media_base64, caption=caption)
        except httpx.HTTPStatusError as exc:
            self._log_failure(phone, evolution_client.classify_send_error(exc))

    def _log_failure(self, phone: str, classified: dict) -> None:
        logger.warning(
            "WhatsAppChannel.deliver falhou: phone=%s error_kind=%s",
            phone,
            classified.get("error_kind"),
        )


__all__ = ["WhatsAppChannel"]
