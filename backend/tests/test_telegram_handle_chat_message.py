"""Testes do handler Telegram → `HandleChatMessage` (task
`unify-message-delivery-pipeline-task-telegram-1`).

Cobre REQ-012 (telegram-channel): `make_message_handler` chama
`HandleChatMessage.execute` com `TelegramChannel` + identidade correta, e
não invoca `agent_runner.run` diretamente.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.infrastructure.channels.telegram_channel import TelegramChannel
from src.infrastructure.telegram import authorization
from src.infrastructure.usage.user_key import telegram_user_key


class _FakeBot:
    """Bot fake — só satisfaz a assinatura de `make_message_handler`."""

    def __init__(self) -> None:
        self.sent: list[tuple[Any, str]] = []

    async def send_message(
        self, chat_id: Any, text: str, *args: Any, **kwargs: Any
    ) -> str:
        self.sent.append((chat_id, text))
        return "message-sent"


@pytest.mark.asyncio
async def test_message_handler_calls_handle_chat_message_not_agent_runner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unit-1: update autorizado → `HandleChatMessage.execute`; zero `run` direto."""
    chat_id = "999"
    thread_id = "resolved-thread-123"
    user_text = "olá do telegram"
    bot = _FakeBot()

    thread_repo = MagicMock(return_value=thread_id)
    monkeypatch.setattr(authorization, "get_or_create_thread_id", thread_repo)

    agent_runner = MagicMock()
    agent_runner.run = AsyncMock()

    execute_mock = AsyncMock()
    with patch(
        "src.infrastructure.telegram.authorization.HandleChatMessage"
    ) as handle_cls:
        handle_cls.return_value.execute = execute_mock

        handler = authorization.make_message_handler(
            authorized_chat_id=chat_id,
            agent_runner=agent_runner,
            bot=bot,
        )

        update = MagicMock()
        update.effective_chat.id = int(chat_id)
        update.message.text = user_text
        context = MagicMock()

        await handler(update, context)

    handle_cls.assert_called_once_with(agent_runner=agent_runner)
    execute_mock.assert_awaited_once()
    kwargs = execute_mock.await_args.kwargs
    assert isinstance(kwargs["channel"], TelegramChannel)
    assert kwargs["user_key"] == telegram_user_key(chat_id)
    assert kwargs["thread_id"] == thread_id
    assert kwargs["text"] == user_text  # raw — sem CHANNEL_INSTRUCTION
    agent_runner.run.assert_not_called()
