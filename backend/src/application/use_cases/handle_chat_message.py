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

from src.application.ports.agent_runner import (
    AgentRunnerPort,
    AgentRunOutcome,
    AgentRunResult,
)
from src.application.ports.chat_channel import ChatChannelPort
from src.domain.scheduling import ToolScope

logger = logging.getLogger(__name__)


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
        """
        if precomputed_output is not None:
            await channel.deliver(
                user_key=user_key,
                text=precomputed_output.text,
                attachments=precomputed_output.attachments,
                kind="normal",
            )
            return

        try:
            result = await self._agent_runner.run(
                thread_id=thread_id,
                prompt=text,
                skills=(),
                tool_scope=ToolScope.RESTRICTED,
                user_key=user_key,
            )
        except Exception as exc:  # noqa: BLE001 — REQ-003: nunca propaga para o handler
            logger.error(
                "agent_run_failed: thread_id=%s error=%s",
                thread_id,
                exc,
            )
            await channel.deliver(
                user_key=user_key,
                text=None,
                attachments=(),
                kind="failure",
            )
            return

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
