"""Testes do roteamento Telegram após `HandleChatMessage` (REQ-012).

Atualizado por `unify-message-delivery-pipeline-task-telegram-1`: o handler
passa o texto cru ao caso de uso (sem `CHANNEL_INSTRUCTION` no prompt —
remoção formal em telegram-2) e não lê `AgentRunResult` diretamente.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.ports.agent_runner import AgentRunResult
from src.infrastructure.telegram import authorization


class _FakeBot:
    """Bot fake: registra `send_message` em `self.sent` sem tocar a rede."""

    def __init__(self) -> None:
        self.sent: list[tuple[Any, str]] = []

    async def send_message(
        self, chat_id: Any, text: str, *args: Any, **kwargs: Any
    ) -> str:  # noqa: ANN401
        self.sent.append((chat_id, text))
        return "message-sent"


def _make_authorized_update(text: str = "olá") -> MagicMock:
    """Monta um `Update` mockado com `chat_id=999` e `text` configuráveis."""
    update = MagicMock()
    update.effective_chat.id = 999
    update.message.text = text
    return update


@pytest.mark.asyncio
async def test_handler_passes_raw_user_text_as_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REQ-012: o prompt enviado ao runner é o texto cru do usuário.

    `CHANNEL_INSTRUCTION` deixa de ser prefixado aqui (formalizado em
    telegram-2 / REQ-013); o handler já entrega `user_text` intacto.
    """
    thread_repo = MagicMock(return_value="resolved-thread-123")
    agent_runner = MagicMock()
    agent_runner.run = AsyncMock()
    monkeypatch.setattr(authorization, "get_or_create_thread_id", thread_repo)

    handler = authorization.make_message_handler(
        authorized_chat_id="999",
        agent_runner=agent_runner,
        bot=_FakeBot(),
    )

    user_text = "olá agente"
    update = _make_authorized_update(text=user_text)
    context = MagicMock()

    await handler(update, context)

    agent_runner.run.assert_called_once()
    assert agent_runner.run.call_args.kwargs["prompt"] == user_text


@pytest.mark.asyncio
async def test_authorization_module_does_not_import_agent_run_result() -> None:
    """REQ-012: `authorization.py` não importa `AgentRunResult` — só o use case."""
    import ast
    from pathlib import Path

    source = Path(authorization.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            names = {alias.name for alias in node.names}
            assert "AgentRunResult" not in names, (
                "authorization.py não deve importar AgentRunResult — "
                "HandleChatMessage consome o DTO"
            )


@pytest.mark.asyncio
async def test_handler_does_not_send_text_directly_to_telegram_on_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Em sucesso sem `output`, o canal NÃO envia texto por conta própria.

    `HandleChatMessage` com `status=ok` e `output=None` não chama `deliver`
    (REQ-003 handle-chat-message). Entrega de sucesso com texto vem do
    `output` capturado — coberta em `test_handle_chat_message.py`.
    """
    run_result = AgentRunResult(thread_id="resolved-thread-123", status="ok", error=None)

    thread_repo = MagicMock(return_value="resolved-thread-123")
    agent_runner = MagicMock()
    agent_runner.run = AsyncMock(return_value=run_result)
    monkeypatch.setattr(authorization, "get_or_create_thread_id", thread_repo)

    fake_bot = _FakeBot()
    handler = authorization.make_message_handler(
        authorized_chat_id="999",
        agent_runner=agent_runner,
        bot=fake_bot,
    )

    update = _make_authorized_update(text="olá")
    context = MagicMock()

    await handler(update, context)

    assert fake_bot.sent == [], (
        f"canal enviou texto em sucesso sem output: {fake_bot.sent!r}"
    )
    assert not hasattr(authorization, "send_message")
    assert not hasattr(authorization, "send_photo")
    assert not hasattr(authorization, "send_document")
