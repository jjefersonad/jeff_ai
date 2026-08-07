"""Caso de uso: executar uma tarefa agendada (disparada pelo scheduler).

Recebe `ScheduledTaskRepositoryPort`, `AgentRunnerPort`, `HandleChatMessage`
e o `ChatChannelPort` de notificação (Scheduled) por injeção. Aplica a
máquina de estado, persiste o resultado e, em sucesso com output, notifica
o destino efetivo (REQ-009/011 + scheduled-channel-routines — save-then-notify,
best-effort).

HITL: `status=interrupted` → `WAITING_HUMAN` + deliver interruption no destino
(não `FAILED`). Overlap `RUNNING`/`WAITING_HUMAN` → no-op (OQ-3).
Cron: após `SUCCEEDED`/`FAILED`, `rearm_for_cron()` antes do save final
(Decision 5 / OQ-1) — `once` permanece terminal.
"""
from __future__ import annotations

import asyncio
import logging

from src.application.ports.agent_runner import AgentRunnerPort, AgentRunResult
from src.application.ports.chat_channel import ChatChannelPort
from src.application.ports.scheduled_task_repository import ScheduledTaskRepositoryPort
from src.application.use_cases.handle_chat_message import HandleChatMessage
from src.domain.scheduling import ScheduledTask, TaskStatus

logger = logging.getLogger(__name__)

_OVERLAP_STATUSES = frozenset({TaskStatus.RUNNING, TaskStatus.WAITING_HUMAN})


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
        """Busca, executa, persiste e (em sucesso/HITL) notifica a tarefa `task_id`.

        Args:
            task_id: Identificador da tarefa a executar.

        Tarefa inexistente (cancelada entre agendamento e disparo) é um
        caso esperado — não levanta exceção. Status `RUNNING` /
        `WAITING_HUMAN` é no-op (overlap de tick cron).
        """
        task = await self._repository.get(task_id)
        if task is None:
            return

        if task.status in _OVERLAP_STATUSES:
            logger.info(
                "scheduled_run_skipped task_id=%s status=%s reason=overlap",
                task_id,
                task.status.value,
            )
            return

        task.start()
        result: AgentRunResult | None = None
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
            elif result.status == "interrupted":
                task.waiting_human()
            else:
                task.fail(result.error or f"Agente retornou status={result.status!r}.")

        should_deliver_interrupt = (
            result is not None and result.status == "interrupted"
        )
        should_notify_ok = (
            result is not None
            and result.status == "ok"
            and result.output is not None
        )

        # Decision 5 / OQ-1: cron terminal → SCHEDULED antes do save final.
        # WAITING_HUMAN NÃO rearma (resume-1 cuida depois do HITL).
        if (
            task.schedule.kind == "cron"
            and task.status in (TaskStatus.SUCCEEDED, TaskStatus.FAILED)
        ):
            task.rearm_for_cron()

        await self._repository.save(task)

        if should_deliver_interrupt:
            await self._deliver_interruption(task=task, result=result)
            return

        if not should_notify_ok:
            if result is not None and result.status == "ok" and result.output is None:
                logger.warning(
                    "scheduled_notify_skipped task_id=%s reason=output_missing",
                    task_id,
                )
            return

        assert result is not None and result.output is not None
        delivery_key = task.effective_delivery_user_key
        if delivery_key is None:
            logger.warning(
                "scheduled_notify_skipped task_id=%s reason=delivery_user_key_missing",
                task_id,
            )
            return

        try:
            await self._handle_chat_message.execute(
                channel=self._notify_channel,
                user_key=delivery_key,
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

    async def _deliver_interruption(
        self,
        *,
        task: ScheduledTask,
        result: AgentRunResult,
    ) -> None:
        """Entrega HITL no destino efetivo (best-effort; status já persistido)."""
        delivery_key = task.effective_delivery_user_key
        if delivery_key is None:
            logger.warning(
                "scheduled_interrupt_skipped task_id=%s reason=delivery_user_key_missing",
                task.id,
            )
            return
        try:
            await self._notify_channel.deliver(
                user_key=delivery_key,
                text=None,
                attachments=(),
                kind="interruption",
                interrupt=result.interrupt,
                thread_id=task.thread_id,
            )
        except Exception as exc:  # noqa: BLE001 — best-effort como notify
            logger.error(
                "scheduled_interrupt_failed task_id=%s error=%s",
                task.id,
                exc,
            )
