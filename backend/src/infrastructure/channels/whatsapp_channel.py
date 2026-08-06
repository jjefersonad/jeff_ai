"""`WhatsAppChannel` — adapter `ChatChannelPort` para o canal WhatsApp (Evolution API).

Encapsula o protocolo de saída Evolution API: texto (`evolution_client.send_text`,
com chunking para textos > 4096 chars), attachments — imagem e documento Office —
via `evolution_client.send_media` (endpoint unificado `/message/sendMedia`), e,
para `kind="interruption"` (change `whatsapp-tool-approval`), um prompt acionável
de aprovação via `evolution_client.send_buttons` — botões nativos reais confirmados
empiricamente contra a instância pinada (spike `whatsapp-tool-approval-task-spike-1`,
2026-08-05), com fallback para um menu numerado em texto (`send_text`) se o envio de
botões falhar explicitamente (REQ-008 whatsapp-channel). O estado da aprovação
pendente é registrado em `whatsapp.approval._pending_approvals`, resolvido depois
pelo webhook (`task-webhook-3`/`task-webhook-4`).

Attachments (`fix-whatsapp-document-delivery-task-adapters-2`): `send_media` exige
`media` como URL — confirmado ao vivo contra a instância real pinada (v2.1.1) que
`/message/sendImage`/`/message/sendDocument` não existem (404) e que `media` em
base64 retorna 500 para qualquer `mediatype`. O adapter NUNCA lê os bytes do
arquivo — apenas minta um token de entrega de uso único
(`delivery_tokens.mint_delivery_token`) para `attachment.path` e monta a URL
`{base_url}/public/media-delivery/{token}`, resolvida depois pela Evolution API via
`GET /public/media-delivery/{token}` (isento de `require_auth`, REQ-014
whatsapp-channel) — os bytes só saem do disco quando essa rota é chamada.

`send_text`/`send_media`/`send_buttons` propagam `httpx.HTTPError` (não engolem, ao
contrário do `bot_client` do Telegram) — este adapter é quem chama
`evolution_client.classify_send_error` e engole, mantendo o mesmo contrato
fail-safe do `ChatChannelPort` (REQ-005 chat-channel-port).

Typing (typing-indicator-chat-channels Decision 6): `send_presence(composing)`
com refresh ~4s; `stop` cancela a task (sem `paused` — API v2.1.1 não expõe).
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from pathlib import Path

import httpx

from src.application.ports.agent_runner import InterruptInfo
from src.application.ports.chat_channel import ChatChannelPort, DeliveryKind
from src.domain.channels import ChannelKind, OutputAttachment
from src.infrastructure.web.delivery_tokens import mint_delivery_token
from src.infrastructure.whatsapp import approval, evolution_client

logger = logging.getLogger(__name__)

_TEXT_CHUNK_LIMIT = 4096
"""Limite de caracteres por mensagem de texto na Evolution API / WhatsApp."""

_IMAGE_MIMES = ("image/png", "image/jpeg", "image/webp", "image/gif")

# Presence `composing` dura ~delay_ms; refresh um pouco antes (Decision 6).
_TYPING_REFRESH_SECONDS = 4.0
_TYPING_PRESENCE_DELAY_MS = 5000


def _delivery_base_url() -> str:
    """Mesma resolução de `composition/dependencies.build_create_document`."""
    return (
        os.getenv("DOCUMENT_BASE_URL") or os.getenv("FRONTEND_ORIGIN") or "http://localhost:3000"
    ).rstrip("/")

_APPROVAL_TITLE = "Aprovação pendente"

# Label → id, na ordem em que os botões/opções aparecem. Ordem e labels
# usados tanto no envio via botões nativos quanto no fallback em texto —
# o webhook (task-webhook-3/4) resolve por texto em ambos os casos (ver
# whatsapp-tool-approval-design, Decision 4: botão-tap chega como texto
# puro, sem payload distinto, confirmado no spike).
_APPROVAL_DECISIONS: tuple[tuple[str, str], ...] = (
    ("approve", "Aprovar"),
    ("reject", "Rejeitar"),
    ("adjust", "Ajustar"),
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


def _require_phone(user_key: str) -> str:
    """Valida `whatsapp:<phone>` não-vazio para typing; levanta `ValueError` se inválido."""
    if not user_key.startswith("whatsapp:"):
        raise ValueError(f"user_key inválido para WhatsApp: {user_key!r}")
    phone = user_key.removeprefix("whatsapp:")
    if not phone:
        raise ValueError(f"user_key sem telefone: {user_key!r}")
    return phone


def _interrupt_description(interrupt: InterruptInfo) -> str:
    """Monta a descrição da ação pendente a partir de `action_requests`.

    Mesma lógica de `telegram/approval._interrupt_description`: usa o
    campo `description` (já capturado por `tier_config._interrupt_description_for`
    antes do interrupt disparar), com `name` como fallback defensivo.
    """
    lines: list[str] = []
    for idx, ar in enumerate(interrupt.action_requests, start=1):
        desc = ar.get("description") or ar.get("name") or "<ação sem descrição>"
        lines.append(f"{idx}. {desc}" if len(interrupt.action_requests) > 1 else desc)
    return "\n".join(lines)


def _approval_menu_text(description: str) -> str:
    """Monta o menu numerado em texto — fallback quando `send_buttons` falha.

    Mesmos labels/ordem de `_APPROVAL_DECISIONS`, numerados 1/2/3 (o
    webhook resolve por texto de qualquer forma — ver Decision 4 do
    design, botão-tap e resposta numérica chegam pelo mesmo campo
    `text`)."""
    options = "\n".join(
        f"{idx}. {label}" for idx, (_, label) in enumerate(_APPROVAL_DECISIONS, start=1)
    )
    return f"{_APPROVAL_TITLE}: {description}\n{options}\nResponda com o número ou o nome da opção."


class WhatsAppChannel(ChatChannelPort):
    """Adapter WhatsApp — construtor recebe o nome da `instance` da Evolution API."""

    def __init__(self, *, instance: str) -> None:
        """Guarda `instance` (usado em toda chamada a `evolution_client`)."""
        self._instance = instance
        self._typing_tasks: dict[str, asyncio.Task[None]] = {}

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
        """Entrega via Evolution API — texto (com chunking), imagem com caption, ou aprovação (botões/fallback)."""
        phone = _phone(user_key)

        if kind == "interruption":
            assert interrupt is not None and thread_id is not None, (
                "kind='interruption' requer interrupt e thread_id (REQ-004 "
                "handle-chat-message cenário 1)"
            )
            await self._send_interruption_prompt(phone, interrupt, thread_id)
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
        try:
            Path(attachment.path).stat()  # falha rápido se ausente, sem ler bytes
            token = mint_delivery_token(attachment.path, attachment.display_name, attachment.mime)
            media_url = f"{_delivery_base_url()}/public/media-delivery/{token}"
            mediatype = "image" if attachment.mime in _IMAGE_MIMES else "document"
            filename = attachment.display_name if mediatype == "document" else None
            await evolution_client.send_media(
                self._instance,
                phone,
                media_url,
                mediatype=mediatype,
                filename=filename,
                caption=caption,
            )
        except Exception as exc:  # noqa: BLE001 — REQ-005: deliver nunca propaga
            if isinstance(exc, httpx.HTTPStatusError):
                self._log_failure(phone, evolution_client.classify_send_error(exc))
            else:
                logger.warning(
                    "WhatsAppChannel.deliver falhou: phone=%s error_kind=unexpected",
                    phone,
                    exc_info=True,
                )

    async def _send_interruption_prompt(
        self, phone: str, interrupt: InterruptInfo, thread_id: str
    ) -> None:
        """Registra a aprovação pendente e envia o prompt (botões, com fallback em texto).

        Ordem: registra `PendingApproval` PRIMEIRO (para que o webhook já
        encontre a pendência mesmo se o cliente responder antes do envio
        terminar de logar), depois tenta os botões nativos, caindo para o
        menu em texto (`_send_text_safe`) se o envio de botões falhar
        explicitamente — REQ-008 cenário 2. Botões nativos confirmados
        funcionais no spike (`task-spike-1`); o fallback nunca foi
        necessário na prática, mas o contrato existe para falhas futuras
        (ex.: instabilidade pontual da Evolution API).
        """
        approval.set_pending_approval(
            phone,
            approval.PendingApproval(
                thread_id=thread_id,
                action_requests=interrupt.action_requests,
                review_configs=interrupt.review_configs,
            ),
        )
        description = _interrupt_description(interrupt)
        buttons = [
            {"type": "reply", "id": decision_id, "text": label}
            for decision_id, label in _APPROVAL_DECISIONS
        ]
        try:
            await evolution_client.send_buttons(
                self._instance,
                phone,
                title=_APPROVAL_TITLE,
                description=description,
                buttons=buttons,
            )
        except Exception:  # noqa: BLE001 — REQ-005: deliver nunca propaga
            logger.warning(
                "WhatsAppChannel.deliver falhou: phone=%s error_kind=unsupported_interactive",
                phone,
                exc_info=True,
            )
            await self._send_text_safe(phone, _approval_menu_text(description))

    def _log_failure(self, phone: str, classified: dict) -> None:
        logger.warning(
            "WhatsAppChannel.deliver falhou: phone=%s error_kind=%s",
            phone,
            classified.get("error_kind"),
        )

    async def start_typing_indicator(self, *, user_key: str) -> None:
        """Envia presence `composing` e mantém refresh até `stop` (Decision 6)."""
        try:
            phone = _require_phone(user_key)
        except ValueError:
            logger.warning(
                "WhatsAppChannel.start_typing_indicator: user_key inválido=%r",
                user_key,
            )
            return

        await self._cancel_typing(user_key)
        await self._send_composing(phone)
        self._typing_tasks[user_key] = asyncio.create_task(
            self._typing_refresh_loop(phone),
            name=f"whatsapp-typing:{user_key}",
        )

    async def stop_typing_indicator(self, *, user_key: str) -> None:
        """Cancela o refresh de typing para `user_key` (idempotente; sem `paused`)."""
        await self._cancel_typing(user_key)

    async def _cancel_typing(self, user_key: str) -> None:
        task = self._typing_tasks.pop(user_key, None)
        if task is None:
            return
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    async def _send_composing(self, phone: str) -> None:
        try:
            await evolution_client.send_presence(
                self._instance,
                phone,
                presence="composing",
                delay_ms=_TYPING_PRESENCE_DELAY_MS,
            )
        except Exception as exc:  # noqa: BLE001 — typing é best-effort
            if isinstance(exc, httpx.HTTPStatusError):
                self._log_failure(phone, evolution_client.classify_send_error(exc))
            else:
                logger.warning(
                    "WhatsAppChannel.typing falhou: phone=%s error_kind=unexpected",
                    phone,
                    exc_info=True,
                )

    async def _typing_refresh_loop(self, phone: str) -> None:
        try:
            while True:
                await asyncio.sleep(_TYPING_REFRESH_SECONDS)
                await self._send_composing(phone)
        except asyncio.CancelledError:
            raise


__all__ = ["WhatsAppChannel"]
