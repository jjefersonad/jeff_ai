"""Caso de uso: `HandleChatMessage` — entrega a resposta do agente ao canal.

Orquestra "usuário disse X → agente respondeu Y → canal entrega Y ao
usuário" para qualquer canal de chat interativo, substituindo a regra
"agente chama tool para entregar" por "canal captura output do agente e
entrega" (spec `handle-chat-message`, ver design
`unify-message-delivery-pipeline`). Corrige o bug de produção onde o
modelo respondia em texto puro sem tool-call e o usuário não recebia nada.
"""
from __future__ import annotations

import logging
import os

from src.application.ports.agent_runner import (
    AgentRunnerPort,
    AgentRunOutcome,
    AgentRunResult,
)
from src.application.ports.chat_channel import ChatChannelPort
from src.domain.channels import ChannelKind
from src.domain.scheduling import ToolScope

logger = logging.getLogger(__name__)

_TYPING_EXCLUDED_KINDS = frozenset({ChannelKind.WEB, ChannelKind.SCHEDULED})
"""Canais cujo `ChatChannelPort` já resolve feedback de forma própria (web
streama tokens via SSE; scheduled delega para outro `user_key`) — REQ-002/
REQ-006 do typing-indicator: o orquestrador não deve nem chamar o port
para esses `channel_kind`s, não basta confiar no no-op do adapter."""


def _typing_enabled() -> bool:
    """Kill-switch de operador sem redeploy.

    `TYPING_INDICATOR_ENABLED` (default `"true"`) — REQ-003 typing-indicator /
    REQ-006 message-delivery-pipeline.
    """
    return os.getenv("TYPING_INDICATOR_ENABLED", "true").strip().lower() != "false"


class HandleChatMessage:
    """Orquestra a execução do agente e a entrega do output via `ChatChannelPort`."""

    def __init__(self, *, agent_runner: AgentRunnerPort) -> None:
        """Recebe o `AgentRunnerPort` por injeção de dependência."""
        self._agent_runner = agent_runner

    async def execute(
        self,
        *,
        channel: ChatChannelPort,
        user_key: str,
        thread_id: str,
        text: str,
        precomputed_output: AgentRunOutcome | None = None,
    ) -> None:
        """Executa o agente para `text` e entrega o output via `channel`.

        Cobre REQ-001/002 (happy path), REQ-003 (falha / output ausente),
        REQ-004 (repassa `interrupt` com `kind="interruption"`), REQ-005
        (propaga `user_key`/`thread_id` sem derivar canal) e REQ-006
        (`deliver` exatamente uma vez por turno com attachments agregados).

        `precomputed_output` (scheduled-tasks REQ-009): quando o caller já
        rodou o agente (ex.: `RunScheduledTask`), entrega esse outcome
        sem reinvocar o runner — evita double-run no notify agendado.

        Typing (typing-indicator-chat-channels): `start` antes do `run` e
        `stop` em `finally` — não tipa no caminho `precomputed_output`, em
        canais `WEB`/`SCHEDULED` (REQ-002/REQ-006), nem com
        `TYPING_INDICATOR_ENABLED=false` (REQ-003).
        """
        if precomputed_output is not None:
            await channel.deliver(
                user_key=user_key,
                text=precomputed_output.text,
                attachments=precomputed_output.attachments,
                kind="normal",
            )
            return

        typing_active = (
            _typing_enabled() and channel.channel_kind not in _TYPING_EXCLUDED_KINDS
        )

        run_failed = False
        result: AgentRunResult | None = None
        if typing_active:
            await channel.start_typing_indicator(user_key=user_key)
        try:
            try:
                result = await self._agent_runner.run(
                    thread_id=thread_id,
                    prompt=text,
                    skills=(),
                    tool_scope=ToolScope.RESTRICTED,
                    user_key=user_key,
                )
            except Exception as exc:  # noqa: BLE001 — REQ-003: nunca propaga para o handler
                run_failed = True
                logger.error(
                    "agent_run_failed: thread_id=%s error=%s",
                    thread_id,
                    exc,
                )
        finally:
            if typing_active:
                await channel.stop_typing_indicator(user_key=user_key)

        if run_failed:
            await channel.deliver(
                user_key=user_key,
                text=None,
                attachments=(),
                kind="failure",
            )
            return

        assert result is not None
        await self._deliver_result(
            channel=channel,
            user_key=user_key,
            thread_id=thread_id,
            result=result,
        )

    async def _deliver_result(
        self,
        *,
        channel: ChatChannelPort,
        user_key: str,
        thread_id: str,
        result: AgentRunResult,
    ) -> None:
        if result.status == "interrupted":
            await channel.deliver(
                user_key=user_key,
                text=None,
                attachments=(),
                kind="interruption",
                interrupt=result.interrupt,
                thread_id=thread_id,
            )
            return

        # Qualquer status ≠ ok (error, timeout, …) → failure (REQ-003).
        if result.status != "ok":
            await channel.deliver(
                user_key=user_key,
                text=None,
                attachments=(),
                kind="failure",
            )
            return

        if result.output is None:
            logger.warning(
                "agent_output_missing: thread_id=%s",
                thread_id,
            )
            return

        await channel.deliver(
            user_key=user_key,
            text=result.output.text,
            attachments=result.output.attachments,
            kind="normal",
        )
