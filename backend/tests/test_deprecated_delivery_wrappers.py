"""Testes dos wrappers deprecated (task
`unify-message-delivery-pipeline-task-cleanup-1`).

Cobre a proposal BREAKING: `send_telegram_message` / `send_whatsapp_message`
permanecem importáveis, logam WARNING de deprecation e delegam ao
`ChatChannelPort` via `ChannelRegistry` (mesmo caminho de `send_message`).
"""
from __future__ import annotations

import logging

import pytest

from src.application.ports.agent_runner import InterruptInfo
from src.application.ports.chat_channel import ChatChannelPort, DeliveryKind
from src.domain.channels import ChannelKind, OutputAttachment
from src.infrastructure.channels.registry import ChannelRegistry
from src.tools import telegram_tools, whatsapp_tools


class _RecordingChannel(ChatChannelPort):
    def __init__(self, kind: ChannelKind) -> None:
        self._kind = kind
        self.calls: list[dict] = []

    @property
    def channel_kind(self) -> ChannelKind:
        return self._kind

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
        self.calls.append(
            {
                "user_key": user_key,
                "text": text,
                "attachments": attachments,
                "kind": kind,
            }
        )


@pytest.fixture(autouse=True)
def _isolated_registry():
    ChannelRegistry.reset()
    yield
    ChannelRegistry.reset()


@pytest.mark.asyncio
async def test_send_telegram_message_logs_deprecation_and_delegates_to_channel(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Unit-1: wrapper deprecated → WARNING + TelegramChannel.deliver."""
    monkeypatch.setenv("TELEGRAM_AUTHORIZED_CHAT_ID", "12345")
    channel = _RecordingChannel(ChannelKind.TELEGRAM)
    ChannelRegistry.register(channel)

    with caplog.at_level(logging.WARNING):
        result = await telegram_tools.send_telegram_message.ainvoke({"text": "oi"})

    assert result == {"success": True}
    assert channel.calls == [
        {
            "user_key": "telegram:12345",
            "text": "oi",
            "attachments": (),
            "kind": "normal",
        }
    ]
    assert any(
        "deprecated" in r.message.lower() and "send_telegram_message" in r.message
        for r in caplog.records
        if r.levelno == logging.WARNING
    )


@pytest.mark.asyncio
async def test_send_whatsapp_message_logs_deprecation_and_delegates_to_channel(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Espelho WhatsApp do unit-1 (mesma migration criteria)."""
    channel = _RecordingChannel(ChannelKind.WHATSAPP)
    ChannelRegistry.register(channel)

    with caplog.at_level(logging.WARNING):
        result = await whatsapp_tools.send_whatsapp_message.ainvoke(
            {"text": "oi", "phone_number": "5511111111111"}
        )

    assert result == {"success": True}
    assert channel.calls == [
        {
            "user_key": "whatsapp:5511111111111",
            "text": "oi",
            "attachments": (),
            "kind": "normal",
        }
    ]
    assert any(
        "deprecated" in r.message.lower() and "send_whatsapp_message" in r.message
        for r in caplog.records
        if r.levelno == logging.WARNING
    )
