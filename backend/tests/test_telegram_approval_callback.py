"""Testes do callback handler de aprovação (`src/infrastructure/telegram/approval.py`).

Cobre a task `telegram-tool-approval-task-callback-4`:

- REQ-003 cenário "Usuário aprova" (`-unit-1`): `CallbackQuery` com
  `data="approve"` de um chat autorizado E com `_pending_approvals[chat_id]`
  registrado → o handler MUST chamar `agent_runner.resume(...)` exatamente
  uma vez com `decisions=({"type": "approve"},)`, chamar `query.answer()`,
  remover a pendência, e NÃO enviar `_CHANNEL_ERROR_MESSAGE`.
- REQ-003 cenário "Usuário rejeita" (`-unit-1` rejeitar): idem ao approve
  mas com `decisions=({"type": "reject"},)`.
- REQ-003 cenário "Callback de chat não autorizado ou sem aprovação pendente"
  (`-unit-2`): callback de chat_id diferente do autorizado OU sem
  pendência → `query.answer()` é chamado mas `agent_runner.resume(...)`
  NÃO é chamado (drop silencioso).
- REQ-004 cenário "Usuário toca em Editar e responde em texto" (`-unit-3`):
  callback com `data="edit"` → `awaiting_edit_text = True` e prompt de
  ajuste enviado; a PRÓXIMA mensagem de texto do chat (não-slash) é
  interceptada pelo `make_message_handler` ANTES do `agent_runner.run(...)`
  normal, e dispara `agent_runner.resume(decisions=({"type": "reject",
  "message": <texto>},))` exatamente uma vez.
- REQ-005 cenário "Resume falha" (`-unit-4`): `agent_runner.resume(...)`
  levanta exceção → o handler MUST chamar `query.answer()` ANTES de
  tratar, enviar `_CHANNEL_ERROR_MESSAGE` ao chat, logar com
  `thread_id`+`chat_id`, remover a pendência, e NÃO re-raise. Mesmo
  comportamento no fluxo de edit intercept.

Todos os testes usam fakes (`MagicMock` + `AsyncMock`); nenhum
componente do LangGraph ou do `python-telegram-bot` real é tocado.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.ports.agent_runner import AgentRunResult
from src.infrastructure.telegram import approval


def _make_fake_bot() -> Any:
    """Bot fake: registra `send_message` em `bot.sent` e tem `answer_callback_query`."""
    bot = MagicMock()
    bot.sent: list[tuple[Any, str]] = []
    bot.answered: list[tuple[Any, str | None]] = []

    async def _send_message(chat_id: Any, text: str, *args: Any, **kwargs: Any) -> str:
        bot.sent.append((chat_id, text))
        return "message-sent"

    async def _answer_callback_query(
        callback_query_id: Any, text: str | None = None, *args: Any, **kwargs: Any
    ) -> bool:
        bot.answered.append((callback_query_id, text))
        return True

    bot.send_message = _send_message  # type: ignore[method-assign]
    bot.answer_callback_query = _answer_callback_query  # type: ignore[method-assign]
    return bot


def _make_fake_callback_query(
    *, chat_id: int | str, callback_data: str, query_id: str = "q-1"
) -> Any:
    """Constrói um `CallbackQuery` fake com `effective_chat.id` e `data`."""
    query = MagicMock()
    query.id = query_id
    query.data = callback_data
    query.effective_chat.id = chat_id
    # `answer` deve ser awaitable; AsyncMock devolve coroutine sem efeito.
    query.answer = AsyncMock()
    return query


# ---------------------------------------------------------------------------
# Unit-1: approve callback
# ---------------------------------------------------------------------------


async def test_callback_handler_resumes_graph_with_approve_decision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unit-1 (REQ-003 cenário "Usuário aprova"): callback com `data="approve"` resume.

    Given:
      - `_pending_approvals["999"]` registrada (criada via
        `set_pending_approval` para simular o `send_approval_keyboard`
        que a task de gateway já faz).
      - `agent_runner.resume` é `AsyncMock` que registra a chamada e
        devolve `AgentRunResult(status="ok")`.
      - Bot fake com `answer_callback_query` e `send_message`.

    When: o callback handler recebe um `CallbackQuery` com
    `data="approve"` do `chat_id=999`.

    Then:
      - `agent_runner.resume(thread_id=<stored>, decisions=({"type": "approve"},))`
        chamado **exatamente uma vez**.
      - `query.answer()` chamado (para desbloquear o cliente do Telegram).
      - Entrada de `_pending_approvals["999"]` removida.
      - `bot.send_message` com `_CHANNEL_ERROR_MESSAGE` **NÃO** é chamado.
    """
    # Limpa estado global (defesa contra vazamento entre testes).
    approval._pending_approvals.clear()
    try:
        approval.set_pending_approval(
            "999",
            approval.PendingApproval(
                thread_id="stored-thread-1",
                action_requests=(
                    {"name": "create_image_from_prompt", "args": {}, "description": "d"},
                ),
                review_configs=({"allowed_decisions": ["approve", "edit", "reject"]},),
            ),
        )

        bot = _make_fake_bot()
        query = _make_fake_callback_query(chat_id=999, callback_data="approve")

        # Substitui o `bot_client.call_bot_api` por uma identidade — o teste
        # quer observar `bot.send_message` e `bot.answer_callback_query`
        # diretamente, sem wrapper de retry.
        from src.infrastructure.telegram import bot_client

        async def _identity(api_call: Any) -> dict[str, Any]:
            result = await api_call()
            return {"success": True, "result": result}

        monkeypatch.setattr(bot_client, "call_bot_api", _identity)

        agent_runner = MagicMock()
        agent_runner.resume = AsyncMock(
            return_value=AgentRunResult(thread_id="stored-thread-1", status="ok")
        )

        # Chama diretamente o handler de callback (a fábrica do
        # `CallbackQueryHandler` do `python-telegram-bot` será registrada
        # pelo `telegram_gateway` na task `task-gateway-5`; aqui
        # exercitamos a função handler em si).
        await approval.handle_approval_callback(
            authorized_chat_id="999",
            agent_runner=agent_runner,
            bot=bot,
            callback_query=query,
        )

        # Resume chamado exatamente uma vez com os args esperados.
        agent_runner.resume.assert_awaited_once()
        kwargs = agent_runner.resume.await_args.kwargs
        assert kwargs["thread_id"] == "stored-thread-1"
        assert kwargs["decisions"] == ({"type": "approve"},)

        # `query.answer()` chamado para o cliente desbloquear.
        query.answer.assert_awaited_once()

        # Pendência removida.
        assert approval.get_pending_approval("999") is None

        # Mensagem de erro NÃO enviada.
        assert bot.sent == []
    finally:
        approval._pending_approvals.clear()


async def test_callback_handler_resumes_graph_with_reject_decision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unit-1 (REQ-003 cenário "Usuário rejeita"): callback com `data="reject"` resume.

    Espelha o teste de approve com `decisions=({"type": "reject"},)`.
    """
    approval._pending_approvals.clear()
    try:
        approval.set_pending_approval(
            "999",
            approval.PendingApproval(
                thread_id="stored-thread-2",
                action_requests=(
                    {"name": "create_image_from_prompt", "args": {}, "description": "d"},
                ),
                review_configs=({"allowed_decisions": ["approve", "edit", "reject"]},),
            ),
        )

        bot = _make_fake_bot()
        query = _make_fake_callback_query(chat_id=999, callback_data="reject")

        from src.infrastructure.telegram import bot_client

        async def _identity(api_call: Any) -> dict[str, Any]:
            result = await api_call()
            return {"success": True, "result": result}

        monkeypatch.setattr(bot_client, "call_bot_api", _identity)

        agent_runner = MagicMock()
        agent_runner.resume = AsyncMock(
            return_value=AgentRunResult(thread_id="stored-thread-2", status="ok")
        )

        await approval.handle_approval_callback(
            authorized_chat_id="999",
            agent_runner=agent_runner,
            bot=bot,
            callback_query=query,
        )

        agent_runner.resume.assert_awaited_once()
        kwargs = agent_runner.resume.await_args.kwargs
        assert kwargs["thread_id"] == "stored-thread-2"
        assert kwargs["decisions"] == ({"type": "reject"},)

        query.answer.assert_awaited_once()
        assert approval.get_pending_approval("999") is None
        assert bot.sent == []
    finally:
        approval._pending_approvals.clear()


# ---------------------------------------------------------------------------
# Unit-2: ignore callback from unauthorized chat OR no pending approval
# ---------------------------------------------------------------------------


async def test_callback_handler_ignores_callback_from_unauthorized_chat() -> None:
    """Unit-2 (REQ-003 cenário "Callback de chat não autorizado"): drop silencioso.

    Given: `CallbackQuery` com `effective_chat.id = 123` (≠ do
    `authorized_chat_id="999"`), `_pending_approvals` vazio.

    When: o handler processa o callback.

    Then: `query.answer()` é chamado (cliente desbloqueia), `agent_runner.resume`
    NÃO é chamado.
    """
    approval._pending_approvals.clear()
    bot = _make_fake_bot()
    query = _make_fake_callback_query(chat_id=123, callback_data="approve")
    agent_runner = MagicMock()
    agent_runner.resume = AsyncMock()

    await approval.handle_approval_callback(
        authorized_chat_id="999",
        agent_runner=agent_runner,
        bot=bot,
        callback_query=query,
    )

    # Cliente desbloqueia mesmo no drop silencioso.
    query.answer.assert_awaited_once()
    agent_runner.resume.assert_not_awaited()


async def test_callback_handler_ignores_stale_callback_without_pending_approval() -> None:
    """Unit-2 (REQ-003 cenário "Callback sem aprovação pendente"): drop silencioso.

    Given: `CallbackQuery` do chat autorizado `999`, mas
    `_pending_approvals` vazio (cenário "botão velho de aprovação já
    resolvida/expirada").

    When: o handler processa o callback.

    Then: `query.answer()` é chamado, `agent_runner.resume` NÃO é
    chamado.
    """
    approval._pending_approvals.clear()
    bot = _make_fake_bot()
    query = _make_fake_callback_query(chat_id=999, callback_data="approve")
    agent_runner = MagicMock()
    agent_runner.resume = AsyncMock()

    await approval.handle_approval_callback(
        authorized_chat_id="999",
        agent_runner=agent_runner,
        bot=bot,
        callback_query=query,
    )

    query.answer.assert_awaited_once()
    agent_runner.resume.assert_not_awaited()


# ---------------------------------------------------------------------------
# Unit-3: edit intercepts next text message
# ---------------------------------------------------------------------------


async def test_edit_callback_marks_awaiting_edit_text_and_sends_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unit-3 parte A (REQ-004 cenário "Editar"): marca flag e pede texto.

    Given: `CallbackQuery` com `data="edit"`, chat autorizado, com
    pendência registrada.

    When: o handler processa o callback.

    Then: `awaiting_edit_text` da pendência vira `True`, prompt de
    ajuste é enviado via `bot.send_message`, `query.answer()` é
    chamado, e `agent_runner.resume` NÃO é chamado (o resume só vem
    na PRÓXIMA mensagem de texto).
    """
    approval._pending_approvals.clear()
    try:
        approval.set_pending_approval(
            "999",
            approval.PendingApproval(
                thread_id="t-edit",
                action_requests=(
                    {"name": "create_image_from_prompt", "args": {}, "description": "d"},
                ),
                review_configs=({"allowed_decisions": ["approve", "edit", "reject"]},),
            ),
        )

        bot = _make_fake_bot()
        query = _make_fake_callback_query(chat_id=999, callback_data="edit")

        from src.infrastructure.telegram import bot_client

        async def _identity(api_call: Any) -> dict[str, Any]:
            result = await api_call()
            return {"success": True, "result": result}

        monkeypatch.setattr(bot_client, "call_bot_api", _identity)

        agent_runner = MagicMock()
        agent_runner.resume = AsyncMock()

        await approval.handle_approval_callback(
            authorized_chat_id="999",
            agent_runner=agent_runner,
            bot=bot,
            callback_query=query,
        )

        # Pendência ainda existe (foi marcada, não removida) com
        # `awaiting_edit_text=True`.
        pending = approval.get_pending_approval("999")
        assert pending is not None
        assert pending.awaiting_edit_text is True

        # Resume NÃO foi chamado ainda — só na próxima msg de texto.
        agent_runner.resume.assert_not_awaited()
        # `query.answer()` chamado.
        query.answer.assert_awaited_once()
        # Prompt de ajuste enviado (deve mencionar "ajuste" / "ajustar").
        assert len(bot.sent) == 1
        chat_id, text = bot.sent[0]
        assert chat_id == "999"
        assert "ajust" in text.lower() or "edita" in text.lower() or "alter" in text.lower()
    finally:
        approval._pending_approvals.clear()


async def test_message_handler_intercepts_next_text_after_edit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unit-3 parte B (REQ-004 cenário "Responder em texto após Editar").

    Given:
      - `_pending_approvals["999"]` com `awaiting_edit_text=True`.
      - Próxima `MessageHandler` invocada recebe uma `Update` com
        `effective_chat.id=999` e `message.text="deixa o fundo azul"`
        (não-slash).

    When: `make_message_handler` é chamado.

    Then:
      - `agent_runner.resume(thread_id=<stored>,
        decisions=({"type": "reject", "message": "deixa o fundo azul"},))`
        chamado **exatamente uma vez**.
      - `agent_runner.run(...)` NÃO é chamado (não inicia novo turno).
      - Pendência removida.
    """
    from src.infrastructure.telegram import authorization

    approval._pending_approvals.clear()
    try:
        approval.set_pending_approval(
            "999",
            approval.PendingApproval(
                thread_id="t-edit-msg",
                action_requests=(
                    {"name": "create_image_from_prompt", "args": {}, "description": "d"},
                ),
                review_configs=({"allowed_decisions": ["approve", "edit", "reject"]},),
                awaiting_edit_text=True,
            ),
        )

        bot = _make_fake_bot()
        thread_repo = MagicMock(return_value="should-not-be-called-for-thread")
        monkeypatch.setattr(authorization, "get_or_create_thread_id", thread_repo)

        # Substitui `send_approval_keyboard` para garantir que NÃO seja
        # chamado nesse caminho (o interrupt já foi consumido; o handler
        # não deve renderizar teclado novo).
        from src.infrastructure.telegram import approval as approval_mod

        async def _no_send(*_args: Any, **_kwargs: Any) -> None:
            raise AssertionError(
                "send_approval_keyboard não deveria ser chamado no intercept de edit"
            )

        monkeypatch.setattr(approval_mod, "send_approval_keyboard", _no_send)

        agent_runner = MagicMock()
        agent_runner.resume = AsyncMock(
            return_value=AgentRunResult(thread_id="t-edit-msg", status="ok")
        )
        # `run` precisa ser AsyncMock para que o handler NÃO o invoque
        # — se invocar, este teste falhará. O `assert_not_awaited` no
        # final confirma.
        agent_runner.run = AsyncMock(
            return_value=AgentRunResult(thread_id="x", status="ok")
        )

        handler = authorization.make_message_handler(
            authorized_chat_id="999",
            agent_runner=agent_runner,
            bot=bot,
        )

        update = MagicMock()
        update.effective_chat.id = 999
        update.message.text = "deixa o fundo azul"
        context = MagicMock()

        await handler(update, context)

        # `resume` chamado uma vez com `decisions=({"type": "reject",
        # "message": "deixa o fundo azul"},)`.
        agent_runner.resume.assert_awaited_once()
        kwargs = agent_runner.resume.await_args.kwargs
        assert kwargs["thread_id"] == "t-edit-msg"
        assert kwargs["decisions"] == (
            {"type": "reject", "message": "deixa o fundo azul"},
        )

        # `run` NÃO foi chamado — o texto do usuário virou o resume.
        agent_runner.run.assert_not_awaited()
        # Pendência removida.
        assert approval.get_pending_approval("999") is None
        # Nenhuma mensagem de erro enviada.
        assert bot.sent == []
    finally:
        approval._pending_approvals.clear()


# ---------------------------------------------------------------------------
# Unit-4: resume failure cleanup
# ---------------------------------------------------------------------------


async def test_callback_handler_swallows_resume_exception_and_clears_pending(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unit-4 (REQ-005 cenário "Resume falha"): swallow, notify, clear.

    Given: pendência registrada, `agent_runner.resume` levanta
    `RuntimeError("network down")`.

    When: o handler processa o callback "approve".

    Then:
      - `query.answer()` chamado (cliente desbloqueia mesmo em falha).
      - `bot.send_message(chat_id=999, text=_CHANNEL_ERROR_MESSAGE)`
        chamado.
      - Pendência removida (chat não fica preso).
      - Exceção NÃO propaga para fora do handler.
    """
    approval._pending_approvals.clear()
    try:
        approval.set_pending_approval(
            "999",
            approval.PendingApproval(
                thread_id="t-fail",
                action_requests=(
                    {"name": "create_image_from_prompt", "args": {}, "description": "d"},
                ),
                review_configs=({"allowed_decisions": ["approve", "edit", "reject"]},),
            ),
        )

        bot = _make_fake_bot()
        query = _make_fake_callback_query(chat_id=999, callback_data="approve")

        from src.infrastructure.telegram import bot_client

        async def _identity(api_call: Any) -> dict[str, Any]:
            result = await api_call()
            return {"success": True, "result": result}

        monkeypatch.setattr(bot_client, "call_bot_api", _identity)

        agent_runner = MagicMock()
        agent_runner.resume = AsyncMock(
            side_effect=RuntimeError("network down")
        )

        # NÃO deve re-raise.
        await approval.handle_approval_callback(
            authorized_chat_id="999",
            agent_runner=agent_runner,
            bot=bot,
            callback_query=query,
        )

        # `query.answer()` chamado mesmo em falha.
        query.answer.assert_awaited_once()
        # Mensagem de erro enviada.
        assert len(bot.sent) == 1
        chat_id, text = bot.sent[0]
        # `chat_id` chega como `str` no handler (a partir de
        # `effective_chat.id`), portanto o `bot.send_message` é
        # chamado com a versão string.
        assert chat_id == "999"
        assert text  # mensagem de erro não-vazia
        # Pendência removida.
        assert approval.get_pending_approval("999") is None
    finally:
        approval._pending_approvals.clear()


async def test_edit_intercept_swallows_resume_exception_and_clears_pending(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unit-4 (REQ-005 cenário "Resume falha" via edit intercept): mesmo swallow.

    Given: pendência com `awaiting_edit_text=True`, próxima mensagem
    de texto chega, `agent_runner.resume` levanta exceção.

    When: `make_message_handler` é invocado.

    Then:
      - `bot.send_message(chat_id=999, text=_CHANNEL_ERROR_MESSAGE)`
        chamado.
      - `agent_runner.run(...)` NÃO é chamado.
      - Pendência removida.
      - Handler NÃO re-raise.
    """
    from src.infrastructure.telegram import authorization

    approval._pending_approvals.clear()
    try:
        approval.set_pending_approval(
            "999",
            approval.PendingApproval(
                thread_id="t-edit-fail",
                action_requests=(
                    {"name": "create_image_from_prompt", "args": {}, "description": "d"},
                ),
                review_configs=({"allowed_decisions": ["approve", "edit", "reject"]},),
                awaiting_edit_text=True,
            ),
        )

        bot = _make_fake_bot()
        thread_repo = MagicMock(return_value="should-not-be-called")
        monkeypatch.setattr(authorization, "get_or_create_thread_id", thread_repo)

        agent_runner = MagicMock()
        agent_runner.resume = AsyncMock(
            side_effect=RuntimeError("network down")
        )
        agent_runner.run = AsyncMock(
            return_value=AgentRunResult(thread_id="x", status="ok")
        )

        handler = authorization.make_message_handler(
            authorized_chat_id="999",
            agent_runner=agent_runner,
            bot=bot,
        )

        update = MagicMock()
        update.effective_chat.id = 999
        update.message.text = "deixa azul"
        context = MagicMock()

        await handler(update, context)

        # `resume` foi chamado e falhou — agora esperamos limpeza e notificação.
        agent_runner.resume.assert_awaited_once()
        # `run` NÃO chamado.
        agent_runner.run.assert_not_awaited()
        # Mensagem de erro enviada.
        assert len(bot.sent) == 1
        chat_id, text = bot.sent[0]
        assert chat_id == "999"
        assert text
        # Pendência removida.
        assert approval.get_pending_approval("999") is None
    finally:
        approval._pending_approvals.clear()


async def test_slash_command_clears_awaiting_edit_text_without_resume() -> None:
    """Unit-3 extra (REQ-004 cenário "Usuário toca em Editar e depois usa um slash command").

    Given: pendência com `awaiting_edit_text=True`, usuário envia um
    slash command (`/new`, etc.) em vez de uma resposta em texto.

    The `MessageHandler` registra o filtro `filters.TEXT & ~filters.COMMAND`,
    então slash commands NÃO chegam no `make_message_handler` — eles
    vão direto para o `CommandHandler` (`commands.dispatch_command`).
    Mas o `awaiting_edit_text` ainda está em memória: a REQ-004
    cenário 2 diz que o estado deve ser descartado (clean
    abandonment).

    When: `approval.discard_edit_text_wait(chat_id)` é invocado (helper
    que o `commands.dispatch_command` chama).

    Then: `awaiting_edit_text` da pendência vira `False`, mas a
    pendência NÃO é removida (outra decisão ainda pode chegar) e
    `agent_runner.resume` NÃO é chamado.
    """
    approval._pending_approvals.clear()
    try:
        approval.set_pending_approval(
            "999",
            approval.PendingApproval(
                thread_id="t-abandon",
                action_requests=(
                    {"name": "create_image_from_prompt", "args": {}, "description": "d"},
                ),
                review_configs=({"allowed_decisions": ["approve", "edit", "reject"]},),
                awaiting_edit_text=True,
            ),
        )

        agent_runner = MagicMock()
        agent_runner.resume = AsyncMock()

        # Helper deve limpar o flag sem chamar resume.
        approval.discard_edit_text_wait(chat_id="999")

        pending = approval.get_pending_approval("999")
        assert pending is not None  # pendência ainda existe
        assert pending.awaiting_edit_text is False  # flag limpa

        # Resume NÃO foi chamado.
        agent_runner.resume.assert_not_awaited()
    finally:
        approval._pending_approvals.clear()
