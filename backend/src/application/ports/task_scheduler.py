"""Port do scheduler de tarefas (REQ-005 do spec `task-scheduling`).

Abstrai o mecanismo de tick (APScheduler no adapter) da camada de
aplicação. O scheduler guarda APENAS o gatilho (`task_id` + trigger) —
nunca o contexto de negócio da tarefa (ver design, seção
"Scheduler como relógio").
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.scheduling import ScheduledTask


class TaskSchedulerPort(ABC):
    """Agenda e desagenda triggers de tarefas.

    A implementação concreta (APScheduler, in-process ticker, etc.) é
    detalhe de infraestrutura — esta porta só conhece a tarefa.
    """

    @abstractmethod
    async def schedule(self, task: ScheduledTask) -> None:
        """Registra o gatilho de `task` para disparar conforme `task.schedule`.

        Idempotente para o mesmo `task.id`: re-agendar substitui o trigger
        existente. Não toca no contexto de negócio da tarefa.
        """
        raise NotImplementedError

    @abstractmethod
    async def unschedule(self, task_id: str) -> None:
        """Remove o gatilho registrado para `task_id` (no-op se inexistente)."""
        raise NotImplementedError
