"""Testes do roteamento com instrução de canal e da disciplina de não-ler-texto-de-resposta.

Cobre a unit `integracao-telegram-task-channel-4-unit-1` (REQ-003 do
`telegram-channel-spec`):

- REQ-003 cenário "Roteamento de uma mensagem autorizada": o `prompt` enviado
  a `AgentRunnerPort.run(...)` inclui a instrução de canal ("responda
  chamando `send_telegram_message`"); o texto original do `Update` é
  preservado, mas prefixado pela instrução.
- REQ-003 (parte do "SHOULD NOT extrair nem enviar texto de resposta"): o
  handler consome o `AgentRunResult` retornado por `runner.run(...)` mas
  NÃO acessa nenhum campo de texto — apenas `status`/`error`. O teste
  garante que o handler NÃO lê atributos que o `AgentRunResult` real
  (`thread_id`, `status`, `error`) não traz — p.ex. `.text`, `.response`,
  `.content`, `.message`.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.ports.agent_runner import AgentRunResult
from src.infrastructure.telegram import authorization

# Substrings obrigatórias da instrução de canal — espelham as tools de
# entrega. Comparamos por substring (não string exata) para não acoplar
# o teste à redação literal do prompt.
_CHANNEL_INSTRUCTION_KEYWORDS = (
    "send_telegram_message",
    "send_telegram_photo",
    "send_telegram_document",
)


class _FakeBot:
    """Bot fake: registra `send_message` em `self.sent` sem tocar a rede.

    Suficiente para satisfazer a assinatura de `make_message_handler`
    introduzida em `task-channel-5` (REQ-005) sem influenciar os
    asserts de REQ-003.
    """

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
async def test_handler_prompt_includes_channel_instruction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REQ-003: o `prompt` enviado ao runner inclui a instrução de canal.

    Verifica que o `prompt` passado a `agent_runner.run(...)` contém a
    substring `send_telegram_message` (o nome da tool de entrega) E contém
    o texto original do usuário, nesta ordem (instrução primeiro, texto
    depois) — para que o agente leia a instrução antes do pedido.
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
    prompt = agent_runner.run.call_args.kwargs["prompt"]

    # A instrução de canal cita a tool de entrega.
    for keyword in _CHANNEL_INSTRUCTION_KEYWORDS:
        assert keyword in prompt, (
            f"esperava que o prompt contivesse {keyword!r} (instrução de canal); "
            f"recebido: {prompt!r}"
        )
    # O texto original do usuário também está presente.
    assert user_text in prompt, (
        f"esperava que o prompt preservasse o texto original do usuário "
        f"({user_text!r}); recebido: {prompt!r}"
    )
    # A instrução de canal precede o texto do usuário (instrução primeiro).
    first_keyword_index = min(prompt.index(k) for k in _CHANNEL_INSTRUCTION_KEYWORDS)
    assert first_keyword_index < prompt.index(user_text), (
        "a instrução de canal deve preceder o texto do usuário no prompt"
    )


@pytest.mark.asyncio
async def test_handler_does_not_read_text_from_agent_run_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REQ-003: o handler NÃO lê nenhum campo de texto de `AgentRunResult`.

    O `AgentRunResult` real só expõe `thread_id`/`status`/`error` (ver
    `src/application/ports/agent_runner.py`). O teste monta um
    `AgentRunResult` válido e configura o mock do runner para devolvê-lo;
    instala um `__getattribute__` instrumentado que registra qualquer
    acesso a atributos sensíveis; depois verifica que o handler NÃO
    acessou `.text`/`.response`/`.content`/`.message`/`.output`/`.choices`/
    `.generations` no DTO.
    """
    run_result = AgentRunResult(
        thread_id="resolved-thread-123",
        status="ok",
        error=None,
    )

    # Introspector: registra qualquer leitura de atributo no
    # `AgentRunResult`. Só `thread_id`, `status` e `error` podem ser lidos;
    # qualquer outro atributo é considerado vazamento de texto de resposta.
    forbidden_attrs: list[str] = []
    original_getattribute = AgentRunResult.__getattribute__

    def _tracking_getattribute(self, name: str) -> object:  # type: ignore[no-untyped-def]
        allowed = {"thread_id", "status", "error"}
        if name not in allowed and not name.startswith("_"):
            forbidden_attrs.append(name)
        return original_getattribute(self, name)

    AgentRunResult.__getattribute__ = _tracking_getattribute  # type: ignore[assignment]
    try:
        thread_repo = MagicMock(return_value="resolved-thread-123")
        agent_runner = MagicMock()
        agent_runner.run = AsyncMock(return_value=run_result)
        monkeypatch.setattr(authorization, "get_or_create_thread_id", thread_repo)

        handler = authorization.make_message_handler(
            authorized_chat_id="999",
            agent_runner=agent_runner,
            bot=_FakeBot(),
        )

        update = _make_authorized_update(text="olá")
        context = MagicMock()

        await handler(update, context)
    finally:
        AgentRunResult.__getattribute__ = original_getattribute  # type: ignore[assignment]

    # Filtra atributos que indicam leitura de texto de resposta.
    text_like = {"text", "response", "content", "message", "output", "choices", "generations"}
    leaked = [name for name in forbidden_attrs if name in text_like]
    assert not leaked, (
        f"handler leu atributo(s) de texto de resposta do AgentRunResult: {leaked!r} "
        f"— AgentRunResult só carrega thread_id/status/error; resposta deve "
        f"ser entregue via tool send_telegram_message, não via retorno do runner."
    )


@pytest.mark.asyncio
async def test_handler_does_not_send_text_directly_to_telegram_on_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REQ-003 (corolário): o handler NÃO envia texto de resposta por conta própria.

    Como o canal só envia texto em caso de falha (REQ-005, `task-channel-5`),
    numa execução de sucesso o handler NÃO pode tocar em nenhum cliente do
    Telegram. Este teste espiona o módulo `authorization` para detectar
    qualquer acoplamento a cliente de envio.
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

    # O canal NÃO envia texto em sucesso — a entrega é responsabilidade
    # do agente chamando `send_telegram_message` (tool). O caminho de
    # ENVIO DIRETO só é exercido em caso de falha (REQ-005, coberto em
    # `test_telegram_channel_failure.py`).
    assert fake_bot.sent == [], (
        f"canal enviou texto em sucesso: {fake_bot.sent!r} — entrega de "
        "sucesso é responsabilidade do agente, não do canal"
    )
    # Hygiene: o módulo `authorization` não deve expor método de envio
    # direto (sem `send_*` no escopo do módulo). O uso de `bot_client`
    # é interno (importado para o caminho de falha REQ-005) e o bot é
    # injetado, não construído dentro do módulo.
    assert not hasattr(authorization, "send_message")
    assert not hasattr(authorization, "send_photo")
    assert not hasattr(authorization, "send_document")
