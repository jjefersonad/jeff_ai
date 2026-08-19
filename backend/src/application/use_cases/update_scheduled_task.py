"""Caso de uso: editar uma tarefa agendada.

Recebe as portas `ScheduledTaskRepositoryPort` e `TaskSchedulerPort` por
injeção de dependência, busca a tarefa, valida ownership/admin e status,
aplica os campos alterados e re-registra o trigger se o `schedule` mudou.

Cobre REQ-009 do delta `task-scheduling` (change `agendamento-jeff-cli-frontend`):
- Dono OU `role=admin` edita uma tarefa `SCHEDULED` normalmente.
- Não-dono sem ser admin → `ScheduledTaskAuthorizationError` (mesmo tipo usado
  por `CancelScheduledTask`).
- Tarefa fora de `SCHEDULED` → `ScheduledTaskNotEditableError`.

`delivery_channel` (scheduled-channel-routines): resolvido via
`ResolveDeliveryTarget` antes de `save` — sem vínculo não persiste mudança.

`profile_id` (multi-agent-profiles-runtime / REQ-009): omitido (`UNSET`)
mantém o valor; `None` limpa o overlay; string valida dono+ativo antes
de persistir — inválido não re-registra trigger.
"""
from __future__ import annotations

from typing import Any, Protocol

from src.application.ports.scheduled_task_repository import ScheduledTaskRepositoryPort
from src.application.ports.task_scheduler import TaskSchedulerPort
from src.application.use_cases.cancel_scheduled_task import (
    ScheduledTaskAuthorizationError,
)
from src.application.use_cases.create_scheduled_task import resolve_scheduled_profile_id
from src.application.use_cases.get_agent_profile import GetAgentProfile
from src.domain.scheduling import Schedule, ScheduledTask, TaskStatus, ToolScope
from src.domain.shared.errors import DomainError

UNSET: Any = object()


class DeliveryTargetResolver(Protocol):
    """Contrato mínimo de `ResolveDeliveryTarget.resolve` (testável com fake)."""

    async def resolve(
        self, *, user_id: str, delivery_channel: str | None
    ) -> str | None:
        """Resolve o destino de entrega do caller autenticado."""
        ...


class ScheduledTaskNotEditableError(Exception):
    """Tentativa de editar uma `ScheduledTask` que não está em `SCHEDULED`.

    Tipo próprio (REQ-009) — distinto de `ScheduledTaskAuthorizationError`
    (chamador sem permissão) e de `DomainError` (invariante de entidade
    violada). O `__init__` aceita `task_id` e `status` para tornar a
    mensagem acionável sem precisar rebuildá-la no handler.
    """

    def __init__(self, *, task_id: str, status: TaskStatus) -> None:
        """Captura contexto suficiente para uma mensagem acionável."""
        self.task_id = task_id
        self.status = status
        super().__init__(
            f"Tarefa {task_id!r} não pode ser editada: status atual é "
            f"{status.value!r}, edição só é permitida em status "
            f"{TaskStatus.SCHEDULED.value!r}."
        )


class UpdateScheduledTask:
    """Orquestra a edição de uma `ScheduledTask` (repo + scheduler).

    Depende apenas das portas; não conhece Postgres, APScheduler nem
    qualquer adapter concreto.
    """

    def __init__(
        self,
        *,
        repository: ScheduledTaskRepositoryPort,
        scheduler: TaskSchedulerPort,
        delivery_resolver: DeliveryTargetResolver,
        get_agent_profile: GetAgentProfile | None = None,
    ) -> None:
        """Recebe as implementações das portas por injeção de dependência."""
        self._repository = repository
        self._scheduler = scheduler
        self._delivery_resolver = delivery_resolver
        self._get_agent_profile = get_agent_profile

    async def execute(
        self,
        *,
        task_id: str,
        caller_user_key: str,
        is_admin: bool,
        prompt: str | None = None,
        schedule: Schedule | None = None,
        tool_scope: ToolScope | None = None,
        skills: tuple[str, ...] | None = None,
        delivery_channel: str | None = None,
        caller_user_id: str | None = None,
        profile_id: str | None | object = UNSET,
    ) -> ScheduledTask | None:
        """Aplica os campos fornecidos e re-agenda se o `schedule` mudou.

        Args:
            task_id: Identificador da tarefa a editar.
            caller_user_key: Identidade do chamador (mesma convenção do
                `CancelScheduledTask.execute`).
            is_admin: True se o chamador tem `role=admin`.
            prompt, schedule, tool_scope, skills: campos opcionais — apenas
                os fornecidos (não-`None`) são alterados.
            delivery_channel: Se informado, resolve e grava
                `delivery_user_key` (requer `caller_user_id`).
            caller_user_id: UUID do chamador — necessário com
                `delivery_channel`.
            profile_id: Overlay; omitido (`UNSET`) mantém o atual; `None`
                limpa para overlay no-op; string valida as mesmas regras 422
                do create (perfil do dono, ativo).

        Returns:
            A tarefa persistida, ou `None` se `task_id` não existir (no-op
            tolerante, mesma convenção de `CancelScheduledTask`).

        Raises:
            ScheduledTaskAuthorizationError: chamador não é dono nem admin.
            ScheduledTaskNotEditableError: tarefa não está em `SCHEDULED`.
            DomainError: destino de entrega inválido / sem vínculo, ou
                `profile_id` inválido.
        """
        task = await self._repository.get(task_id)
        if task is None:
            return None

        is_owner = task.owner_user_key == caller_user_key
        if not (is_owner or is_admin):
            raise ScheduledTaskAuthorizationError(
                task_id=task_id, caller_user_key=caller_user_key
            )

        if task.status is not TaskStatus.SCHEDULED:
            raise ScheduledTaskNotEditableError(task_id=task_id, status=task.status)

        if delivery_channel is not None:
            if not caller_user_id:
                raise DomainError(
                    "delivery_channel exige caller_user_id do caller autenticado"
                )
            task.delivery_user_key = await self._delivery_resolver.resolve(
                user_id=caller_user_id,
                delivery_channel=delivery_channel,
            )

        schedule_changed = schedule is not None and schedule != task.schedule

        if prompt is not None:
            task.prompt = prompt
        if schedule is not None:
            task.schedule = schedule
        if tool_scope is not None:
            task.tool_scope = tool_scope
        if skills is not None:
            task.skills = tuple(skills)
        if profile_id is not UNSET:
            if profile_id is None:
                task.profile_id = None
            else:
                task.profile_id = await resolve_scheduled_profile_id(
                    self._get_agent_profile,
                    owner_user_id=_profile_owner_user_id(task, caller_user_id),
                    profile_id=str(profile_id),
                )

        await self._repository.save(task)

        if schedule_changed:
            await self._scheduler.unschedule(task_id)
            await self._scheduler.schedule(task)

        return task


def _profile_owner_user_id(
    task: ScheduledTask, caller_user_id: str | None
) -> str | None:
    """UUID do dono da tarefa para validar `profile_id` (não o do admin)."""
    key = task.owner_user_key or ""
    if key.startswith("web:"):
        return key.removeprefix("web:")
    return caller_user_id
