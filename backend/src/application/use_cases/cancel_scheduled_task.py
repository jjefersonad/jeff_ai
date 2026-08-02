"""Caso de uso: cancelar uma tarefa agendada.

Recebe as portas `ScheduledTaskRepositoryPort` e `TaskSchedulerPort` por
injeção de dependência, busca a tarefa, valida ownership e remove tanto
a linha do banco quanto o trigger do scheduler.

Cobre REQ-004 e REQ-008 do spec `task-scheduling`:
- Dono OU `role=admin` cancela normalmente.
- Não-dono sem ser admin → `ScheduledTaskAuthorizationError` (explícito,
  distinto de "não encontrado", que continua no-op tolerante).
"""
from __future__ import annotations

from src.application.ports.scheduled_task_repository import ScheduledTaskRepositoryPort
from src.application.ports.task_scheduler import TaskSchedulerPort


class ScheduledTaskAuthorizationError(Exception):
    """Tentativa de cancelar tarefa agendada sem ser dono nem admin.

    Tipo próprio (REQ-008) — distinto de `DomainError` (invariante de
    entidade violada) e de qualquer outro erro genérico. O caller (tool
    Tier 2) traduz para uma mensagem clara para o agente, sem stack
    trace crua. O `__init__` aceita `caller_user_key` e `task_id` para
    tornar a mensagem acionável sem precisar rebuildá-la no handler.
    """

    def __init__(self, *, task_id: str, caller_user_key: str) -> None:
        """Captura contexto suficiente para uma mensagem acionável.

        Args:
            task_id: ID da tarefa que o chamador tentou cancelar.
            caller_user_key: Identidade do chamador que não tem permissão.
        """
        self.task_id = task_id
        self.caller_user_key = caller_user_key
        super().__init__(
            f"Usuário {caller_user_key!r} não tem permissão para cancelar "
            f"a tarefa {task_id!r}: não é o dono e não tem role=admin."
        )


class CancelScheduledTask:
    """Orquestra o cancelamento de uma `ScheduledTask` (repo + scheduler).

    Depende apenas das portas; não conhece Postgres, APScheduler nem
    qualquer adapter concreto.
    """

    def __init__(
        self,
        *,
        repository: ScheduledTaskRepositoryPort,
        scheduler: TaskSchedulerPort,
    ) -> None:
        """Recebe as implementações das portas por injeção de dependência."""
        self._repository = repository
        self._scheduler = scheduler

    async def execute(
        self,
        *,
        task_id: str,
        caller_user_key: str,
        is_admin: bool,
    ) -> None:
        """Remove a tarefa e seu trigger (REQ-004/REQ-008).

        Args:
            task_id: Identificador da tarefa a cancelar.
            caller_user_key: Identidade do chamador (mesma convenção do
                `ListScheduledTasks.execute`).
            is_admin: True se o chamador tem `role=admin`.

        Raises:
            ScheduledTaskAuthorizationError: Quando a tarefa existe, mas
                o chamador não é dono e não é admin. Nunca levantado
                para `task_id` inexistente — esse caso é no-op
                tolerante.
        """
        task = await self._repository.get(task_id)

        # Caso tolerante: tarefa inexistente — não é erro, pode ter sido
        # cancelada por outra janela/owner entre a listagem e o clique.
        if task is None:
            await self._repository.delete(task_id)  # no-op, mantém idempotência
            return

        # Autorização: dono OU admin (REQ-004 / REQ-008). Verificada antes
        # de qualquer efeito colateral para que o erro não deixe
        # estado parcial (desagendou mas não removeu, ou vice-versa).
        is_owner = task.owner_user_key == caller_user_key
        if not (is_owner or is_admin):
            raise ScheduledTaskAuthorizationError(
                task_id=task_id, caller_user_key=caller_user_key
            )

        # Ordem: desagenda primeiro (mais barato de reverter se a remoção
        # do banco falhar) e remove do banco depois.
        await self._scheduler.unschedule(task_id)
        await self._repository.delete(task_id)
