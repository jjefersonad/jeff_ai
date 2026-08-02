"""Caso de uso: listar tarefas agendadas.

Recebe `ScheduledTaskRepositoryPort` por injeção de dependência e delega a
filtragem ao port: quando o chamador é `admin` retorna `list_all()`, caso
contrário `list_by_owner(caller_user_key)`.

Cobre REQ-004 e REQ-008 do spec `task-scheduling` (escopo de listagem por
`owner_user_key`, com bypass para `role=admin`).
"""
from __future__ import annotations

from src.application.ports.scheduled_task_repository import ScheduledTaskRepositoryPort
from src.domain.scheduling import ScheduledTask


class ListScheduledTasks:
    """Lista tarefas agendadas escopadas ao chamador.

    Depende apenas da porta de repositório; não conhece Postgres nem
    qualquer adapter concreto. O caller (tool Tier 2) resolve
    `caller_user_key` do `configurable` do run e `is_admin` da role do
    usuário — esta classe não tem como saber disso.
    """

    def __init__(self, *, repository: ScheduledTaskRepositoryPort) -> None:
        """Recebe a porta de repositório por injeção de dependência."""
        self._repository = repository

    async def execute(
        self,
        *,
        caller_user_key: str,
        is_admin: bool,
    ) -> list[ScheduledTask]:
        """Retorna as tarefas visíveis ao chamador (REQ-004).

        Args:
            caller_user_key: Identidade do chamador (`web:<id>` /
                `telegram:<chat_id>`). O caller DEVE tê-lo resolvido do
                `configurable` do run atual.
            is_admin: True se o chamador tem `role=admin` (bypass de
                ownership). Resolvido pelo caller via `get_user_by_id` /
                convenção Telegram.

        Returns:
            Lista de `ScheduledTask` (pode ser vazia). Quando `is_admin`,
            inclui tarefas de todos os owners; caso contrário, só do
            `caller_user_key`.
        """
        if is_admin:
            return await self._repository.list_all()
        return await self._repository.list_by_owner(caller_user_key)
