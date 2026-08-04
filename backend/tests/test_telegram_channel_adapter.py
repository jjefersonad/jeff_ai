"""Testes do adapter `TelegramChannel` (task `unify-message-delivery-pipeline-task-adapters-1`).

Cobre REQ-011/REQ-014 (telegram-channel) e REQ-001/REQ-003/REQ-005
(chat-channel-port):

- texto sem attachment → `bot.send_message`, chat_id parseado do `user_key`.
- `RetryAfter` é engolido (via `bot_client.call_bot_api`, já testado
  isoladamente em `test_bot_client.py`) e logado como WARN — nunca propaga.
- attachment de imagem → `bot.send_photo`; attachment de documento →
  `bot.send_document`; texto e mídia na mesma chamada (caption).
- `kind="interruption"` → `approval.send_approval_keyboard(...)`.
"""
from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram.error import RetryAfter

from src.application.ports.agent_runner import InterruptInfo
from src.domain.channels import ChannelKind, OutputAttachment
from src.infrastructure.channels.telegram_channel import TelegramChannel


def _make_bot() -> MagicMock:
    bot = MagicMock()
    bot.send_message = AsyncMock(return_value=MagicMock())
    bot.send_photo = AsyncMock(return_value=MagicMock())
    bot.send_document = AsyncMock(return_value=MagicMock())
    return bot


def test_channel_kind_is_telegram() -> None:
    channel = TelegramChannel(bot=_make_bot())

    assert channel.channel_kind is ChannelKind.TELEGRAM


@pytest.mark.asyncio
async def test_deliver_text_only_calls_send_message_with_parsed_chat_id() -> None:
    bot = _make_bot()
    channel = TelegramChannel(bot=bot)

    await channel.deliver(user_key="telegram:123", text="Olá!", attachments=(), kind="normal")

    bot.send_message.assert_awaited_once_with(chat_id=123, text="Olá!")


@pytest.mark.asyncio
async def test_deliver_swallows_rate_limit_and_logs_warning(caplog: pytest.LogCaptureFixture) -> None:
    bot = _make_bot()
    bot.send_message = AsyncMock(side_effect=RetryAfter(retry_after=30))
    channel = TelegramChannel(bot=bot)

    with caplog.at_level(logging.WARNING):
        await channel.deliver(user_key="telegram:123", text="Olá!", attachments=(), kind="normal")

    assert any(
        "rate_limited" in record.message and record.levelno == logging.WARNING
        for record in caplog.records
    )


@pytest.mark.asyncio
async def test_deliver_image_attachment_calls_send_photo_with_caption(tmp_path) -> None:
    image_path = tmp_path / "foo.png"
    image_path.write_bytes(b"fake-png-bytes")
    bot = _make_bot()
    channel = TelegramChannel(bot=bot)
    attachment = OutputAttachment(path=str(image_path), mime="image/png", display_name="foo.png")

    await channel.deliver(
        user_key="telegram:123", text="Aqui está", attachments=(attachment,), kind="normal"
    )

    bot.send_photo.assert_awaited_once()
    _, kwargs = bot.send_photo.await_args
    assert kwargs["chat_id"] == 123
    assert kwargs["caption"] == "Aqui está"
    assert kwargs["photo"] == b"fake-png-bytes"
    bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_deliver_document_attachment_calls_send_document_with_caption(tmp_path) -> None:
    doc_path = tmp_path / "foo.docx"
    doc_path.write_bytes(b"fake-docx-bytes")
    bot = _make_bot()
    channel = TelegramChannel(bot=bot)
    attachment = OutputAttachment(
        path=str(doc_path),
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        display_name="foo.docx",
    )

    await channel.deliver(
        user_key="telegram:123", text="Aqui está", attachments=(attachment,), kind="normal"
    )

    bot.send_document.assert_awaited_once()
    _, kwargs = bot.send_document.await_args
    assert kwargs["chat_id"] == 123
    assert kwargs["caption"] == "Aqui está"
    assert kwargs["document"] == b"fake-docx-bytes"


@pytest.mark.asyncio
async def test_deliver_failure_sends_friendly_default_message() -> None:
    """kind=failure com text=None → mensagem amigável do canal (DeliveryKind)."""
    bot = _make_bot()
    channel = TelegramChannel(bot=bot)

    await channel.deliver(
        user_key="telegram:123", text=None, attachments=(), kind="failure"
    )

    bot.send_message.assert_awaited_once()
    _, kwargs = bot.send_message.await_args
    assert kwargs["chat_id"] == 123
    assert kwargs["text"]
    assert "falha" in kwargs["text"].lower()


@pytest.mark.asyncio
async def test_deliver_interruption_calls_send_approval_keyboard() -> None:
    bot = _make_bot()
    channel = TelegramChannel(bot=bot)
    interrupt = InterruptInfo(action_requests=({"name": "x"},), review_configs=({"allowed_decisions": ["approve"]},))

    with patch(
        "src.infrastructure.channels.telegram_channel.approval.send_approval_keyboard",
        new_callable=AsyncMock,
    ) as send_keyboard_mock:
        await channel.deliver(
            user_key="telegram:123",
            text=None,
            attachments=(),
            kind="interruption",
            interrupt=interrupt,
            thread_id="thread-1",
        )

    send_keyboard_mock.assert_awaited_once()
    _, kwargs = send_keyboard_mock.await_args
    assert kwargs["bot"] is bot
    assert kwargs["chat_id"] == "123"
    assert kwargs["thread_id"] == "thread-1"
    assert kwargs["interrupt"] is interrupt
