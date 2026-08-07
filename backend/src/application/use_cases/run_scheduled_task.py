"""Caso de uso: executar uma tarefa agendada (disparada pelo scheduler).

Recebe `ScheduledTaskRepositoryPort`, `AgentRunnerPort`, `HandleChatMessage`
e o `ChatChannelPort` de notificação (Scheduled) por injeção. Aplica a
máquina de estado, persiste o resultado e, em sucesso com output, notifica
o owner (REQ-009/011 scheduled-tasks — save-then-notify, best-effort).
"""
from __future__ import annotations

import asyncio
import logging

from src.application.ports.agent_runner import AgentRunnerPort
from src.application.ports.chat_channel import ChatChannelPort
from src.application.ports.scheduled_task_repository import ScheduledTaskRepositoryPort
from src.application.use_cases.handle_chat_message import HandleChatMessage

logger = logging.getLogger(__name__)


class RunScheduledTask:
    """Orquestra uma execução isolada de `ScheduledTask` (repo + agent + notify).

    Depende apenas das portas e do caso de uso de entrega; não conhece
    Postgres, APScheduler nem adapters concretos de canal. O caller
    (`jeff_cli.py`) monta esta classe com os adapters injetados em runtime.
    """

    def __init__(
        self,
        *,
        repository: ScheduledTaskRepositoryPort,
        agent_runner: AgentRunnerPort,
        handle_chat_message: HandleChatMessage,
        notify_channel: ChatChannelPort,
    ) -> None:
        """Recebe as implementações das portas por injeção de dependência."""
        self._repository = repository
        self._agent_runner = agent_runner
        self._handle_chat_message = handle_chat_message
        self._notify_channel = notify_channel

    async def execute(self, *, task_id: str) -> None:
        """Busca, executa, persiste e (em sucesso) notifica a tarefa `task_id`.

        Args:
            task_id: Identificador da tarefa a executar.

        Tarefa inexistente (cancelada entre agendamento e disparo) é um
        caso esperado — não levanta exceção.
        """
        task = await self._repository.get(task_id)
        if task is None:
            return

        task.start()
        result = None
        try:
            result = await asyncio.wait_for(
                self._agent_runner.run(
                    thread_id=task.thread_id,
                    prompt=task.prompt,
                    skills=task.skills,
                    tool_scope=task.tool_scope,
                    user_key=task.owner_user_key,
                ),
                timeout=task.timeout_seconds,
            )
        except TimeoutError:
            task.fail(
                f"Execução excedeu o timeout de {task.timeout_seconds}s."
            )
        except Exception as exc:  # noqa: BLE001 - qualquer falha do agente vira FAILED
            task.fail(str(exc))
        else:
            if result.status == "ok":
                task.succeed()
            else:
                task.fail(result.error or f"Agente retornou status={result.status!r}.")

        await self._repository.save(task)

        if result is None or result.status != "ok":
            return

        if result.output is None:
            logger.warning(
                "scheduled_notify_skipped task_id=%s reason=output_missing",
                task_id,
            )
            return

        try:
            await self._handle_chat_message.execute(
                channel=self._notify_channel,
                user_key=task.owner_user_key,
                thread_id=task.thread_id,
                text=result.output.text or "",
                precomputed_output=result.output,
            )
        except Exception as exc:  # noqa: BLE001 — REQ-011: notify best-effort
            logger.error(
                "scheduled_notify_failed task_id=%s error=%s",
                task_id,
                exc,
            )
