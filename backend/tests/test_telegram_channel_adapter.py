"""Testes do adapter `TelegramChannel` (task `unify-message-delivery-pipeline-task-adapters-1`).

Cobre REQ-011/REQ-014 (telegram-channel) e REQ-001/REQ-003/REQ-005
(chat-channel-port):

- texto sem attachment → `bot.send_message`, chat_id parseado do `user_key`.
- `RetryAfter` é engolido (via `bot_client.call_bot_api`, já testado
  isoladamente em `test_bot_client.py`) e logado como WARN — nunca propaga.
- attachment de imagem → `bot.send_photo`; attachment de documento →
  `bot.send_document`; texto e mídia na mesma chamada (caption).
- `kind="interruption"` → `approval.send_approval_keyboard(...)`.

Typing (typing-indicator-chat-channels-task-telegram-adapter-1):
- `start_typing_indicator` → `send_chat_action(typing)` + refresh cancelável.
"""
from __future__ import annotations

import asyncio
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
    bot.send_chat_action = AsyncMock(return_value=MagicMock())
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


# ---------------------------------------------------------------------------
# typing-indicator-chat-channels-task-telegram-adapter-1
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_typing_indicator_sends_chat_action_typing() -> None:
    """Unit-1: start envia sendChatAction typing (REQ-001)."""
    bot = _make_bot()
    channel = TelegramChannel(bot=bot)

    await channel.start_typing_indicator(user_key="telegram:1234")
    try:
        bot.send_chat_action.assert_awaited_once_with(chat_id=1234, action="typing")
    finally:
        await channel.stop_typing_indicator(user_key="telegram:1234")


@pytest.mark.asyncio
async def test_start_typing_invalid_user_key_does_not_raise(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Unit-2a: user_key inválido não propaga (REQ-001)."""
    bot = _make_bot()
    channel = TelegramChannel(bot=bot)

    with caplog.at_level(logging.WARNING):
        result = await channel.start_typing_indicator(user_key="telegram:not-an-int")

    assert result is None
    bot.send_chat_action.assert_not_awaited()


@pytest.mark.asyncio
async def test_start_typing_swallows_bot_api_failure(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Unit-2b: falha da Bot API no start não propaga (REQ-002)."""
    bot = _make_bot()
    bot.send_chat_action = AsyncMock(side_effect=RetryAfter(retry_after=5))
    channel = TelegramChannel(bot=bot)

    with caplog.at_level(logging.WARNING):
        result = await channel.start_typing_indicator(user_key="telegram:1234")

    assert result is None
    await channel.stop_typing_indicator(user_key="telegram:1234")


@pytest.mark.asyncio
async def test_stop_typing_cancels_refresh_and_second_start_replaces() -> None:
    """Unit-3: stop cancela refresh; segundo start substitui (REQ-002 / REQ-ADD-001)."""
    bot = _make_bot()
    channel = TelegramChannel(bot=bot)

    with patch(
        "src.infrastructure.channels.telegram_channel._TYPING_REFRESH_SECONDS",
        0.05,
    ):
        await channel.start_typing_indicator(user_key="telegram:1234")
        first_task = channel._typing_tasks["telegram:1234"]
        assert not first_task.done()

        await channel.start_typing_indicator(user_key="telegram:1234")
        second_task = channel._typing_tasks["telegram:1234"]
        assert first_task is not second_task
        assert first_task.cancelled() or first_task.done()

        await channel.stop_typing_indicator(user_key="telegram:1234")
        assert "telegram:1234" not in channel._typing_tasks
        assert second_task.cancelled() or second_task.done()

        # stop sem start correspondente é seguro
        await channel.stop_typing_indicator(user_key="telegram:1234")

    # refresh loop deve ter reenviado action além do start inicial
    assert bot.send_chat_action.await_count >= 1
    # dá um tick para o loop cancelado assentar
    await asyncio.sleep(0)
