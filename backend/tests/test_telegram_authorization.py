"""Testes do filtro de allowlist de chat_id (`src/infrastructure/telegram/authorization.py`).

Cobre as tasks `integracao-telegram-task-channel-2` e `-task-channel-3`:

- REQ-002 cenário "Mensagem de chat não autorizado" (task-channel-2): update
  de chat_id diferente do `TELEGRAM_AUTHORIZED_CHAT_ID` deve ser descartado —
  `is_authorized_chat` devolve `False` e o handler construído
  (`make_message_handler`) NÃO chama `get_or_create_thread_id` nem invoca o
  agente.
- REQ-002 cenário "Mensagem do chat autorizado" (task-channel-2): update do
  chat_id autorizado prossegue — `is_authorized_chat` devolve `True` e o
  handler chama `get_or_create_thread_id` (proxy de "próxima etapa de
  processamento").
- REQ-001 cenário "Mensagem subsequente do mesmo chat" (task-channel-3):
  para um update autorizado, o handler chama `get_or_create_thread_id(chat_id)`
  exatamente uma vez E propaga o `thread_id` retornado para a chamada
  seguinte a `agent_runner.run(...)` (a invocação concreta do run com prompt
  e skills é responsabilidade de `task-channel-4`).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.infrastructure.telegram import authorization


class _FakeBot:
    """Bot fake: registra `send_message` em `self.sent` sem tocar a rede.

    Suficiente para a fronteira do handler (REQ-005), que usa
    `bot_client.call_bot_api(lambda: bot.send_message(...))`. Esses
    tests verificam o caminho de SUCESSO e/ou DROPPING — em ambos o bot
    é injetado para satisfazer a assinatura do `make_message_handler`
    mas não deve ser chamado.
    """

    def __init__(self) -> None:
        self.sent: list[tuple[Any, str]] = []

    async def send_message(
        self, chat_id: Any, text: str, *args: Any, **kwargs: Any
    ) -> str:  # noqa: ANN401
        self.sent.append((chat_id, text))
        return "message-sent"


def test_is_authorized_chat_returns_false_for_unauthorized_chat() -> None:
    """`is_authorized_chat` rejeita chat_id diferente do configurado (REQ-002)."""
    assert authorization.is_authorized_chat("111", "222") is False


def test_is_authorized_chat_returns_true_for_authorized_chat() -> None:
    """`is_authorized_chat` aceita chat_id igual ao configurado (REQ-002)."""
    assert authorization.is_authorized_chat("999", "999") is True


def test_is_authorized_chat_treats_empty_string_as_no_match() -> None:
    """chat_id vazio contra configurado não-vazio é sempre não autorizado.

    Cobre a defesa em profundidade contra updates malformados que não tragam
    `chat_id` — não devem ser processados.
    """
    assert authorization.is_authorized_chat("", "999") is False


async def test_resolve_authorization_via_real_binding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REQ-002 delta `telegram-channel` cenário 1: chat com vínculo real em
    `user_integrations` é autorizado e resolve o `user_id` real — mesmo sem
    bater com o `TELEGRAM_AUTHORIZED_CHAT_ID` legado (task `channel-1`)."""
    monkeypatch.setattr(
        authorization, "resolve_telegram_user_id", AsyncMock(return_value="user-linked")
    )
    authorized, user_id = await authorization.resolve_authorization("555", "999")
    assert authorized is True
    assert user_id == "user-linked"


async def test_resolve_authorization_via_legacy_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REQ-002 delta `telegram-channel` cenário 2: chat_id igual ao legado é
    autorizado sem tocar `user_integrations` (fallback da janela de
    migração), e não resolve `user_id` real."""
    resolve_mock = AsyncMock(return_value="should-not-be-called")
    monkeypatch.setattr(authorization, "resolve_telegram_user_id", resolve_mock)
    authorized, user_id = await authorization.resolve_authorization("999", "999")
    assert authorized is True
    assert user_id is None
    resolve_mock.assert_not_called()


async def test_resolve_authorization_denies_when_neither_path_matches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REQ-002 delta `telegram-channel` cenário 3: chat_id sem vínculo real e
    diferente do legado não é autorizado."""
    monkeypatch.setattr(
        authorization, "resolve_telegram_user_id", AsyncMock(return_value=None)
    )
    authorized, user_id = await authorization.resolve_authorization("555", "999")
    assert authorized is False
    assert user_id is None


async def test_message_handler_drops_unauthorized_update(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Handler descarta update de chat não autorizado — sem chamar thread_repo nem agente.

    `get_or_create_thread_id` e o callable do agente são mockados; se o handler
    chamá-los, o teste falha (cenário REQ-002 "Mensagem de chat não autorizado").
    `resolve_telegram_user_id` também é mockado (sem vínculo) — isola este
    teste do Postgres real; a resolução via vínculo real é coberta por
    `test_user_integration_credentials_e2e.py`.
    """
    thread_repo = MagicMock()
    agent_runner = MagicMock()
    # O handler chama `agent_runner.run(...)` apenas para updates autorizados,
    # mas como ele é `async def`, configuramos `run` como `AsyncMock` para
    # não levantar em `await` caso o handler o invoque por engano.
    agent_runner.run = AsyncMock()
    monkeypatch.setattr(authorization, "get_or_create_thread_id", thread_repo)
    monkeypatch.setattr(authorization, "resolve_telegram_user_id", AsyncMock(return_value=None))

    handler = authorization.make_message_handler(
        authorized_chat_id="999",
        agent_runner=agent_runner,
        bot=_FakeBot(),
    )

    update = MagicMock()
    update.effective_chat.id = 123  # != "999"
    context = MagicMock()

    await handler(update, context)

    thread_repo.assert_not_called()
    agent_runner.run.assert_not_called()


async def test_message_handler_resolves_thread_id_for_authorized_update(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Handler resolve e propaga o `thread_id` para `agent_runner.run` (REQ-001).

    Cobre a unit `integracao-telegram-task-channel-3-unit-1`: para um update
    autorizado, `get_or_create_thread_id(chat_id)` é chamado exatamente uma
    vez e o `thread_id` retornado é propagado como o `thread_id` da chamada
    a `agent_runner.run(...)`. O `prompt`/`skills`/`tool_scope` efetivos
    dessa chamada são responsabilidade de `task-channel-4`; este teste só
    verifica que a propagação do `thread_id` acontece.
    """
    thread_repo = MagicMock(return_value="resolved-thread-123")
    agent_runner = MagicMock()
    # `run` é `async def` no port real — `AsyncMock` devolve uma coroutine
    # awaitable sem levantar em `await handler(...)`. Não importa o retorno:
    # a unit só verifica a chamada.
    agent_runner.run = AsyncMock()
    monkeypatch.setattr(authorization, "get_or_create_thread_id", thread_repo)

    handler = authorization.make_message_handler(
        authorized_chat_id="999",
        agent_runner=agent_runner,
        bot=_FakeBot(),
    )

    update = MagicMock()
    update.effective_chat.id = 999
    update.message.text = "olá"
    context = MagicMock()

    await handler(update, context)

    # REQ-001: `get_or_create_thread_id(chat_id)` chamado exatamente uma vez.
    thread_repo.assert_called_once_with("999")
    # REQ-001: o `thread_id` retornado é o `thread_id` passado a
    # `agent_runner.run(thread_id=...)`. Outros kwargs (prompt/skills/scope)
    # ainda não são responsabilidade desta task.
    agent_runner.run.assert_called_once()
    _call_kwargs = agent_runner.run.call_args.kwargs
    assert _call_kwargs["thread_id"] == "resolved-thread-123"


async def test_message_handler_dispatches_to_approval_when_status_interrupted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unit-3 (`telegram-tool-approval-task-approval-3`): interrupt → teclado, não `_notify_failure`.

    Quando `agent_runner.run()` devolve `AgentRunResult(status="interrupted",
    interrupt=...)`, o handler MUST chamar
    `approval.send_approval_keyboard(bot, chat_id, thread_id, interrupt)` e
    MUST NOT cair no branch de falha (`_notify_failure`/bot.send_message
    com texto de erro). Cobre REQ-002 do
    `telegram-tool-approval-spec`.
    """
    from src.application.ports.agent_runner import AgentRunResult, InterruptInfo
    from src.infrastructure.telegram import approval

    thread_repo = MagicMock(return_value="t1")
    interrupt = InterruptInfo(
        action_requests=({"name": "x", "args": {}, "description": "d"},),
        review_configs=({"allowed_decisions": ["approve", "edit", "reject"]},),
    )
    runner_result = AgentRunResult(
        thread_id="t1", status="interrupted", interrupt=interrupt
    )
    agent_runner = MagicMock()
    agent_runner.run = AsyncMock(return_value=runner_result)
    monkeypatch.setattr(authorization, "get_or_create_thread_id", thread_repo)

    send_approval_called: dict[str, Any] = {}

    async def _fake_send_approval(
        bot: Any, chat_id: str, thread_id: str, interrupt: Any
    ) -> None:
        send_approval_called["called"] = True
        send_approval_called["bot"] = bot
        send_approval_called["chat_id"] = chat_id
        send_approval_called["thread_id"] = thread_id
        send_approval_called["interrupt"] = interrupt

    monkeypatch.setattr(approval, "send_approval_keyboard", _fake_send_approval)

    bot = _FakeBot()
    handler = authorization.make_message_handler(
        authorized_chat_id="999",
        agent_runner=agent_runner,
        bot=bot,
    )

    update = MagicMock()
    update.effective_chat.id = 999
    update.message.text = "gera imagem"
    context = MagicMock()

    await handler(update, context)

    # O handler deve ter delegado para `send_approval_keyboard` com os
    # argumentos corretos.
    assert send_approval_called.get("called") is True
    assert send_approval_called["bot"] is bot
    assert send_approval_called["chat_id"] == "999"
    assert send_approval_called["thread_id"] == "t1"
    assert send_approval_called["interrupt"] is interrupt
    # E NÃO deve ter chamado bot.send_message com a mensagem de falha
    # (REQ-005 caminho de erro preservado mas NÃO acionado para "interrupted").
    assert bot.sent == []
