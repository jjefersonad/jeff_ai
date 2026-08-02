"""Testes de `src/infrastructure/telegram/start_command.py` (`/start <code>`).

Cobre a task `user-integration-credentials-task-linking-2`:

- unit-1 (REQ-002 cenário 1): `/start <código válido>` chama a use case de
  redenção exatamente uma vez e responde ao chat com uma confirmação de
  sucesso.
- unit-2 (REQ-002 cenários 2/3): `/start <código inválido>` responde com um
  erro legível e NÃO propaga exceção para fora do handler — mesma fronteira
  de falha usada por `authorization.py`/`commands.py`.

Não há allowlist de `chat_id` aqui (diferente de `commands.py`): o próprio
propósito do `/start` é vincular um chat ainda não autorizado.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

from src.application.use_cases.redeem_telegram_link_code import (
    TelegramLinkCodeInvalidError,
)
from src.infrastructure.telegram import start_command


class _FakeBot:
    """Bot fake: registra `send_message` em `self.sent` sem tocar a rede."""

    def __init__(self) -> None:
        self.sent: list[tuple[Any, str]] = []

    async def send_message(
        self, chat_id: Any, text: str, *args: Any, **kwargs: Any
    ) -> str:  # noqa: ANN401
        self.sent.append((chat_id, text))
        return "message-sent"


def _make_update(chat_id: Any, text: str) -> MagicMock:
    update = MagicMock()
    update.effective_chat.id = chat_id
    update.message.text = text
    return update


async def test_start_command_valid_code_confirms_success_and_calls_use_case_once() -> None:
    bot = _FakeBot()
    redeem_use_case = AsyncMock()
    handler = start_command.make_start_command_handler(
        redeem_use_case=redeem_use_case, bot=bot
    )
    update = _make_update("chat-1", "/start ABC123")

    await handler(update, MagicMock())

    redeem_use_case.execute.assert_awaited_once_with(code="ABC123", chat_id="chat-1")
    assert len(bot.sent) == 1
    assert bot.sent[0][0] == "chat-1"


async def test_start_command_invalid_code_replies_with_error_and_does_not_raise() -> None:
    bot = _FakeBot()
    redeem_use_case = AsyncMock()
    redeem_use_case.execute.side_effect = TelegramLinkCodeInvalidError(
        "Código de vínculo inválido, expirado ou já utilizado."
    )
    handler = start_command.make_start_command_handler(
        redeem_use_case=redeem_use_case, bot=bot
    )
    update = _make_update("chat-1", "/start DOES-NOT-EXIST")

    await handler(update, MagicMock())

    assert len(bot.sent) == 1
    assert bot.sent[0][0] == "chat-1"
    text = bot.sent[0][1]
    assert "traceback" not in text.lower()
    assert "exception" not in text.lower()
