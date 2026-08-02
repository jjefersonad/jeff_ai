"""Roteamento de mensagens WhatsApp autorizadas para o grafo `unified` (REQ-004).

Task `whatsapp-evolution-channel-task-channel-4`: monta o `prompt` prefixado
pela instrução de canal (cita `send_whatsapp_message` pelo nome) e invoca
`AgentRunnerPort.run(thread_id, prompt, skills, tool_scope, user_key)` —
mesmo port e mesmo padrão de `src/infrastructure/telegram/authorization.py`.

`route_authorized_message` repassa o `AgentRunResult` de volta ao chamador
sem inspecionar nem extrair texto dele — a entrega ao usuário é
responsabilidade exclusiva da tool `send_whatsapp_message`, chamada pelo
próprio agente em tool-call. Detectar falha (`status`/`error`) e notificar o
número de origem é escopo de `task-channel-5` (REQ-006), não desta função.
"""
from __future__ import annotations

from typing import Any, Protocol

from src.domain.scheduling import ToolScope

# Instrução de canal injetada como prefixo do `prompt` (REQ-004). Cita a
# tool de entrega pelo nome — mesmo raciocínio de
# `telegram/authorization.CHANNEL_INSTRUCTION`: o DTO do runner não devolve
# texto ao canal, então a entrega só acontece se o agente chamar a tool.
CHANNEL_INSTRUCTION = (
    "[Canal WhatsApp] Esta é uma conversa do usuário via WhatsApp. "
    "A entrega ao usuário SÓ acontece via tool de envio — nunca em texto "
    "livre no reasoning.\n"
    "- Texto: chame `send_whatsapp_message` com o texto da resposta.\n\n"
)


class _AgentRunnerPort(Protocol):
    """Tipo estrutural mínimo — ver `telegram/authorization._AgentRunnerPort`."""

    async def run(self, *args: Any, **kwargs: Any) -> Any: ...


def build_channel_prompt(user_text: str) -> str:
    """Prefixa o texto do usuário com a instrução de canal (REQ-004)."""
    return f"{CHANNEL_INSTRUCTION}{user_text}"


async def route_authorized_message(
    *,
    thread_id: str,
    text: str,
    agent_runner: _AgentRunnerPort,
    user_key: str | None = None,
) -> Any:
    """Roteia `text` para o grafo `unified` via `AgentRunnerPort.run()` (REQ-004).

    Devolve o `AgentRunResult` sem tocar nele — quem chama (o webhook,
    estendido por `task-channel-5`) decide o que fazer com `status`/`error`.
    """
    prompt = build_channel_prompt(text)
    return await agent_runner.run(
        thread_id=thread_id,
        prompt=prompt,
        skills=(),
        tool_scope=ToolScope.RESTRICTED,
        user_key=user_key,
    )


__all__ = ["CHANNEL_INSTRUCTION", "build_channel_prompt", "route_authorized_message"]
