"""Port de repositório de tarefas agendadas (REQ-001 do spec `task-scheduling`).

Abstrai a persistência de `ScheduledTask` (Postgres no adapter) do
restante da camada de aplicação. `get()` retorna `None` para tarefa
inexistente — NUNCA levanta exceção.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.scheduling import ScheduledTask


class ScheduledTaskRepositoryPort(ABC):
    """Persiste o contexto completo de cada tarefa agendada (REQ-001).

    Implementações devem ser idempotentes em `save()` e tolerantes a
    tarefa inexistente em `get()` e `delete()`.
    """

    @abstractmethod
    async def save(self, task: ScheduledTask) -> None:
        """Cria ou atualiza a tarefa persistida (id é a chave primária)."""
        raise NotImplementedError

    @abstractmethod
    async def get(self, task_id: str) -> ScheduledTask | None:
        """Retorna a tarefa pelo `task_id` ou `None` se não existir.

        Nunca levanta exceção para `task_id` inexistente — o caller
        decide o que fazer (criar, falhar, retornar 404).
        """
        raise NotImplementedError

    @abstractmethod
    async def list_all(self) -> list[ScheduledTask]:
        """Retorna todas as tarefas agendadas (em qualquer estado)."""
        raise NotImplementedError

    @abstractmethod
    async def delete(self, task_id: str) -> None:
        """Remove a tarefa. Tolerante a `task_id` inexistente (no-op)."""
        raise NotImplementedError
