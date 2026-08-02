"""Testes de propagação de `user_key` Telegram (recording-2 unit-2).

Cobre `track-user-token-usage-task-recording-2-unit-2` (REQ-002):

- WHEN o message handler autorizado chama o agent_runner
- THEN o `user_key` passado/configurado é `telegram:<chat_id>` do Update
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.infrastructure.telegram import authorization
from src.infrastructure.usage.user_key import telegram_user_key


class _FakeBot:
    """Bot fake: registra `send_message` sem tocar a rede."""

    def __init__(self) -> None:
        self.sent: list[tuple[Any, str]] = []

    async def send_message(
        self, chat_id: Any, text: str, *args: Any, **kwargs: Any
    ) -> str:  # noqa: ANN401
        self.sent.append((chat_id, text))
        return "message-sent"


async def test_message_handler_passes_telegram_user_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unit-2: handler autorizado propaga `telegram:<chat_id>` ao runner."""
    chat_id = "999"
    thread_repo = MagicMock(return_value="resolved-thread-123")
    agent_runner = MagicMock()
    agent_runner.run = AsyncMock()
    monkeypatch.setattr(authorization, "get_or_create_thread_id", thread_repo)

    handler = authorization.make_message_handler(
        authorized_chat_id=chat_id,
        agent_runner=agent_runner,
        bot=_FakeBot(),
    )

    update = MagicMock()
    update.effective_chat.id = int(chat_id)
    update.message.text = "olá"
    context = MagicMock()

    await handler(update, context)

    agent_runner.run.assert_called_once()
    kwargs = agent_runner.run.call_args.kwargs
    assert kwargs["user_key"] == telegram_user_key(chat_id)
    assert kwargs["user_key"] == "telegram:999"
