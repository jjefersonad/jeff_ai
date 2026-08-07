"""Caso de uso: completar tarefa agendada após resume HITL.

Quando o usuário aprova/rejeita uma interrupção numa thread que tem
tarefa `WAITING_HUMAN`, este use case aplica a transição terminal e
rearma cron se aplicável (Decision 4 / REQ-003 scheduled-human-intervention).

Sem tarefa `WAITING_HUMAN` para a `thread_id` → no-op (chat normal).
"""
from __future__ import annotations

import logging
from typing import Literal

from src.application.ports.scheduled_task_repository import ScheduledTaskRepositoryPort
from src.domain.scheduling import ScheduledTask, TaskStatus

logger = logging.getLogger(__name__)

ResumeOutcome = Literal["succeeded", "failed"]


class CompleteScheduledTaskAfterResume:
    """Fecha o ciclo HITL de uma `ScheduledTask` em `WAITING_HUMAN`."""

    def __init__(self, *, repository: ScheduledTaskRepositoryPort) -> None:
        self._repository = repository

    async def execute(
        self,
        *,
        thread_id: str,
        outcome: ResumeOutcome,
        error: str | None = None,
    ) -> ScheduledTask | None:
        """Aplica sucesso/falha à tarefa `WAITING_HUMAN` da `thread_id`.

        Args:
            thread_id: Thread do resume HITL (mesma da tarefa agendada).
            outcome: `"succeeded"` (approve/ok) ou `"failed"` (reject/erro).
            error: Mensagem opcional em falha (default genérico).

        Returns:
            A tarefa persistida após a transição, ou `None` se não houver
            tarefa `WAITING_HUMAN` para a thread (no-op).
        """
        task = await self._find_waiting_human(thread_id)
        if task is None:
            return None

        if outcome == "succeeded":
            task.resume_succeed()
        else:
            task.resume_fail(error or "Interrupção rejeitada ou resume falhou.")

        if task.schedule.kind == "cron" and task.status in (
            TaskStatus.SUCCEEDED,
            TaskStatus.FAILED,
        ):
            task.rearm_for_cron()

        await self._repository.save(task)
        logger.info(
            "scheduled_task_completed_after_resume task_id=%s thread_id=%s "
            "outcome=%s status=%s",
            task.id,
            thread_id,
            outcome,
            task.status.value,
        )
        return task

    async def _find_waiting_human(self, thread_id: str) -> ScheduledTask | None:
        for task in await self._repository.list_all():
            if (
                task.thread_id == thread_id
                and task.status is TaskStatus.WAITING_HUMAN
            ):
                return task
        return None
