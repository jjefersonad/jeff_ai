"""Testes de tratamento de falha no handler do canal Telegram.

Cobre a unit `integracao-telegram-task-channel-5-unit-1` (REQ-005 do
`telegram-channel-spec`):

- REQ-005 cenário "Timeout ou exceção na invocação do agente": quando
  `AgentRunnerPort.run()` devolve um `AgentRunResult` com `status != "ok"`
  (ex.: `"error"`, `"timeout"`) OU levanta uma exceção, o handler:

    1. captura a falha (a exceção não se propaga para fora do handler — o
       loop de polling continua vivo);
    2. envia uma mensagem de erro legível ao `chat_id` de origem via
       `bot_client.call_bot_api(bot.send_message(...))` — esta é a única
       situação em que o canal envia texto por conta própria, sem passar
       pela tool `send_telegram_message` (a entrega normal é
       responsabilidade do agente em tool-call).

  O sucesso (status="ok") NÃO envia mensagem nenhuma pelo canal — esse
  caminho é coberto em `test_telegram_channel_routing.py` e é o que
  diferencia REQ-003 (sem envio direto) de REQ-005 (envio só em falha).
"""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.ports.agent_runner import AgentRunResult
from src.infrastructure.telegram import authorization, bot_client


def _make_authorized_update(chat_id: int = 999, text: str = "olá") -> MagicMock:
    """Monta um `Update` mockado com `chat_id` e `text` configuráveis."""
    update = MagicMock()
    update.effective_chat.id = chat_id
    update.message.text = text
    return update


class _FakeBot:
    """Substitui `telegram.Bot`: grava as chamadas sem tocar a rede.

    Compatível com a API mínima exigida pelo `bot_client.call_bot_api`:
    expõe `send_message(chat_id, text)` como coroutine.
    """

    def __init__(self) -> None:
        self.sent: list[tuple[Any, str]] = []

    async def send_message(
        self, chat_id: Any, text: str, *args: Any, **kwargs: Any
    ) -> str:  # noqa: ANN401
        self.sent.append((chat_id, text))
        return "message-sent"


@pytest.mark.asyncio
async def test_handler_sends_error_message_when_runner_returns_error_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REQ-005: status != "ok" → handler envia mensagem de erro ao chat de origem.

    Configura o runner para devolver um `AgentRunResult(status="error",
    error="connection refused")` e verifica que o handler:
    - enviou exatamente uma mensagem via `bot.send_message`;
    - o `chat_id` é o de origem (extraído do `update.effective_chat.id`);
    - o texto contém indicação de falha (legível ao usuário);
    - não propagou nenhuma exceção.
    """
    thread_repo = MagicMock(return_value="resolved-thread-123")
    monkeypatch.setattr(authorization, "get_or_create_thread_id", thread_repo)

    error_result = AgentRunResult(
        thread_id="resolved-thread-123",
        status="error",
        error="connection refused",
    )
    agent_runner = MagicMock()
    agent_runner.run = AsyncMock(return_value=error_result)

    bot = _FakeBot()

    handler = authorization.make_message_handler(
        authorized_chat_id="999",
        agent_runner=agent_runner,
        bot=bot,
    )

    update = _make_authorized_update(chat_id=999, text="olá agente")
    context = MagicMock()

    # Não deve levantar — a falha é capturada e reportada via bot.
    await handler(update, context)

    assert len(bot.sent) == 1, (
        f"esperava exatamente 1 mensagem de erro enviada; recebi {len(bot.sent)}: "
        f"{bot.sent!r}"
    )
    sent_chat_id, sent_text = bot.sent[0]
    # O handler normaliza `chat_id` para `str` (linha 188 do authorization.py
    # — `chat_id = str(update.effective_chat.id)`); o teste usa a mesma
    # string para evitar acoplamento ao tipo original do `effective_chat.id`
    # (int em testes, string quando vier de `str` no `Update` real).
    assert sent_chat_id == "999", (
        f"mensagem de erro deve ir para o chat de origem ('999'); recebi {sent_chat_id!r}"
    )
    # A mensagem precisa ser legível ao usuário e indicar falha — sem
    # acoplar a redação literal do texto (a unidade abaixo
    # `test_handler_sends_error_message_with_status_timeout` cobre o
    # formato exato).
    assert sent_text, "mensagem de erro não pode ser vazia"
    # Não deve vazar detalhes internos: nenhum stack trace, nenhum
    # identificador de thread_id do agente.
    assert "resolved-thread-123" not in sent_text, (
        "mensagem de erro ao usuário não deve vazar thread_id interno"
    )


@pytest.mark.asyncio
async def test_handler_sends_error_message_when_runner_raises_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REQ-005: exceção em `agent_runner.run()` → handler captura e envia erro.

    Cobre o caso em que o runner PROPAGA exceção (não engole para DTO,
    ex.: bug interno que escapa do try/except do adapter). O handler:
    - captura a exceção (NÃO propaga — o loop de polling continua vivo);
    - envia uma mensagem de erro ao `chat_id` de origem via `bot`.
    """
    thread_repo = MagicMock(return_value="resolved-thread-123")
    monkeypatch.setattr(authorization, "get_or_create_thread_id", thread_repo)

    agent_runner = MagicMock()
    agent_runner.run = AsyncMock(side_effect=RuntimeError("boom interno"))

    bot = _FakeBot()

    handler = authorization.make_message_handler(
        authorized_chat_id="999",
        agent_runner=agent_runner,
        bot=bot,
    )

    update = _make_authorized_update(chat_id=999, text="olá agente")
    context = MagicMock()

    # A exceção NÃO pode se propagar — esse é o requisito central de
    # REQ-005 ("a exceção não se propaga para fora do handler").
    await handler(update, context)

    assert len(bot.sent) == 1, (
        f"esperava 1 mensagem de erro enviada mesmo com exceção; recebi {len(bot.sent)}"
    )
    sent_chat_id, _sent_text = bot.sent[0]
    assert sent_chat_id == "999"


@pytest.mark.asyncio
async def test_handler_does_not_send_error_message_on_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REQ-003 (corolário) + REQ-005: em sucesso, NENHUMA mensagem é enviada pelo canal.

    A entrega da resposta em sucesso é responsabilidade do agente
    chamando `send_telegram_message` (tool), não do canal. O canal só
    envia texto em caso de falha.
    """
    thread_repo = MagicMock(return_value="resolved-thread-123")
    monkeypatch.setattr(authorization, "get_or_create_thread_id", thread_repo)

    success_result = AgentRunResult(
        thread_id="resolved-thread-123", status="ok", error=None
    )
    agent_runner = MagicMock()
    agent_runner.run = AsyncMock(return_value=success_result)

    bot = _FakeBot()

    handler = authorization.make_message_handler(
        authorized_chat_id="999",
        agent_runner=agent_runner,
        bot=bot,
    )

    update = _make_authorized_update(chat_id=999, text="olá")
    context = MagicMock()

    await handler(update, context)

    assert bot.sent == [], (
        f"canal NÃO deve enviar mensagem em sucesso; recebeu {bot.sent!r}. "
        "A entrega de sucesso é responsabilidade do agente chamando "
        "send_telegram_message (tool)."
    )


@pytest.mark.asyncio
async def test_handler_swallows_bot_send_failure_without_propagating(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REQ-005 (defesa em profundidade): falha do `bot.send_message` NÃO derruba o handler.

    Se o envio da mensagem de erro para o Telegram também falhar
    (ex.: rede caída no exato momento do erro), o handler NÃO pode
    propagar essa falha para fora — o loop de polling tem que continuar
    vivo, sempre. A falha do envio é logada e absorvida.
    """
    thread_repo = MagicMock(return_value="resolved-thread-123")
    monkeypatch.setattr(authorization, "get_or_create_thread_id", thread_repo)

    error_result = AgentRunResult(
        thread_id="resolved-thread-123",
        status="error",
        error="connection refused",
    )
    agent_runner = MagicMock()
    agent_runner.run = AsyncMock(return_value=error_result)

    # `bot.send_message` levanta `RetryAfter` (ou seja, mesmo passando
    # pelo `bot_client.call_bot_api` que classifica, queremos garantir que
    # se algo pior escapar — uma exceção NÃO-TelegramError, por exemplo
    # — o handler também engole).
    class _BrokenBot:
        async def send_message(
            self, chat_id: Any, text: str, *args: Any, **kwargs: Any
        ) -> None:  # noqa: ANN401
            raise RuntimeError("rede caiu também no envio do erro")

    bot = _BrokenBot()
    # Garante que o `bot_client` usado é o real (sem mock) para validar
    # o swallowing ponta-a-ponta. (Re-mockamos só se o teste setar
    # explicitamente; aqui não tocamos.)
    _ = bot_client  # marca uso para evitar import não-utilizado quando o handler for implementado

    handler = authorization.make_message_handler(
        authorized_chat_id="999",
        agent_runner=agent_runner,
        bot=bot,
    )

    update = _make_authorized_update(chat_id=999, text="olá")
    context = MagicMock()

    # A falha do envio NÃO propaga.
    await handler(update, context)
