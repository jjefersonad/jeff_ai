"""Helpers de prompt WhatsApp (legado pós-`HandleChatMessage`).

`CHANNEL_INSTRUCTION` foi removido (REQ-007 / whatsapp-2) — a instrução de
entrega vive no `_SYSTEM_PROMPT` do agente. `build_channel_prompt` devolve
`user_text` sem pre-prefix. `route_authorized_message` permanece como
wrapper fino para callers/testes legados; o webhook usa `HandleChatMessage`.
"""
from __future__ import annotations

from typing import Any, Protocol

from src.domain.scheduling import ToolScope


class _AgentRunnerPort(Protocol):
    """Tipo estrutural mínimo — ver `telegram/authorization._AgentRunnerPort`."""

    async def run(self, *args: Any, **kwargs: Any) -> Any: ...


def build_channel_prompt(user_text: str) -> str:
    """Devolve `user_text` sem pre-prefix (REQ-007).

    A instrução de entrega moveu-se para a seção "Entrega de mensagens"
    do `_SYSTEM_PROMPT` do agente — o prompt do usuário fica só o texto.
    """
    return user_text


async def route_authorized_message(
    *,
    thread_id: str,
    text: str,
    agent_runner: _AgentRunnerPort,
    user_key: str | None = None,
) -> Any:
    """Roteia `text` para o grafo `unified` via `AgentRunnerPort.run()`.

    Wrapper legado — o webhook WhatsApp chama `HandleChatMessage` (whatsapp-1).
    Devolve o `AgentRunResult` sem tocar nele.
    """
    prompt = build_channel_prompt(text)
    return await agent_runner.run(
        thread_id=thread_id,
        prompt=prompt,
        skills=(),
        tool_scope=ToolScope.RESTRICTED,
        user_key=user_key,
    )


__all__ = ["build_channel_prompt", "route_authorized_message"]
