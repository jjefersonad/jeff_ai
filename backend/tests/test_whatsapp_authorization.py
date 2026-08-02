"""Testes de `src.infrastructure.whatsapp.authorization` (REQ-004, task `channel-4`).

Cobre o unit-test linkado à task no OpenSddRag:

- unit-1 (whatsapp-channel REQ-004, cenário "Roteamento de uma mensagem
  autorizada"): o `prompt` passado a `AgentRunnerPort.run()` inclui a
  instrução de canal citando `send_whatsapp_message`, e
  `route_authorized_message` não lê nem envia texto de resposta a partir
  do retorno de `run()`.
"""
from __future__ import annotations

from typing import Any

from src.domain.scheduling import ToolScope
from src.infrastructure.whatsapp.authorization import (
    CHANNEL_INSTRUCTION,
    build_channel_prompt,
    route_authorized_message,
)


class _FakeAgentRunner:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.sentinel_result = object()  # sem atributo de texto — leitura indevida quebraria

    async def run(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return self.sentinel_result


def test_build_channel_prompt_prefixes_instruction() -> None:
    prompt = build_channel_prompt("oi, tudo bem?")

    assert prompt == f"{CHANNEL_INSTRUCTION}oi, tudo bem?"
    assert "send_whatsapp_message" in prompt


async def test_route_authorized_message_calls_run_with_channel_instruction() -> None:
    """whatsapp-evolution-channel-task-channel-4-unit-1."""
    runner = _FakeAgentRunner()

    result = await route_authorized_message(
        thread_id="thread-xyz",
        text="oi, tudo bem?",
        agent_runner=runner,
        user_key="whatsapp:5511111111111",
    )

    assert len(runner.calls) == 1
    call = runner.calls[0]
    assert call["thread_id"] == "thread-xyz"
    assert "send_whatsapp_message" in call["prompt"]
    assert call["prompt"] == build_channel_prompt("oi, tudo bem?")
    assert call["skills"] == ()
    assert call["tool_scope"] == ToolScope.RESTRICTED
    assert call["user_key"] == "whatsapp:5511111111111"
    # a função não deve tentar ler/enviar texto do retorno — apenas o repassa
    # (o sentinel não tem atributo de texto; acessá-lo indevidamente
    # levantaria AttributeError antes deste ponto)
    assert result is runner.sentinel_result
