"""Adapter Postgres de `ScheduledTaskRepositoryPort` (task `agendamento-jeff-cli-task-persistence-2`).

Usa `psycopg` puro (assíncrono) contra a tabela `scheduled_tasks`
(`scheduled_tasks_schema.py`), mesmo padrão de acesso a banco do restante do
projeto (`usage/repository.py`, `telegram/thread_repository.py`) — sem
SQLAlchemy, sem pool compartilhado: cada operação abre e fecha sua própria
conexão, o que serve tanto ao processo do servidor (`webapp.py`) quanto ao
subprocesso `jeff_cli.py` (ver design da mudança).
"""
from __future__ import annotations

from typing import Any

import psycopg

from src.application.ports.scheduled_task_repository import ScheduledTaskRepositoryPort
from src.domain.scheduling import Schedule, ScheduledTask, TaskStatus, ToolScope

_COLUMNS = (
    "id, prompt, thread_id, owner_user_key, delivery_user_key, skills, "
    "tool_scope, schedule_kind, schedule_expr, status, timeout_seconds, "
    "started_at, finished_at, last_error, created_at"
)

_UPSERT = f"""
INSERT INTO scheduled_tasks ({_COLUMNS})
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (id) DO UPDATE SET
    prompt = EXCLUDED.prompt,
    thread_id = EXCLUDED.thread_id,
    owner_user_key = EXCLUDED.owner_user_key,
    delivery_user_key = EXCLUDED.delivery_user_key,
    skills = EXCLUDED.skills,
    tool_scope = EXCLUDED.tool_scope,
    schedule_kind = EXCLUDED.schedule_kind,
    schedule_expr = EXCLUDED.schedule_expr,
    status = EXCLUDED.status,
    timeout_seconds = EXCLUDED.timeout_seconds,
    started_at = EXCLUDED.started_at,
    finished_at = EXCLUDED.finished_at,
    last_error = EXCLUDED.last_error
"""

_SELECT_BY_ID = f"SELECT {_COLUMNS} FROM scheduled_tasks WHERE id = %s"
_SELECT_ALL = f"SELECT {_COLUMNS} FROM scheduled_tasks ORDER BY created_at"
_SELECT_BY_OWNER = f"{_SELECT_ALL.replace('ORDER BY', 'WHERE owner_user_key = %s ORDER BY')}"
_DELETE = "DELETE FROM scheduled_tasks WHERE id = %s"


class PostgresScheduledTaskRepository(ScheduledTaskRepositoryPort):
    """Persiste `ScheduledTask` na tabela `scheduled_tasks` via `psycopg` assíncrono."""

    def __init__(self, conninfo: str) -> None:
        """Guarda o conninfo Postgres para abrir uma conexão por operação."""
        self._conninfo = conninfo

    async def save(self, task: ScheduledTask) -> None:
        """Upsert por `id` (REQ-001) — não sobrescreve `created_at` numa atualização."""
        async with await psycopg.AsyncConnection.connect(self._conninfo) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    _UPSERT,
                    (
                        task.id,
                        task.prompt,
                        task.thread_id,
                        task.owner_user_key,
                        task.delivery_user_key,
                        list(task.skills),
                        task.tool_scope.value,
                        task.schedule.kind,
                        task.schedule.expr,
                        task.status.value,
                        task.timeout_seconds,
                        task.started_at,
                        task.finished_at,
                        task.error,
                        task.created_at,
                    ),
                )
            await conn.commit()

    async def get(self, task_id: str) -> ScheduledTask | None:
        """Retorna a tarefa ou `None` se `task_id` não existir — nunca exceção."""
        async with await psycopg.AsyncConnection.connect(self._conninfo) as conn:
            async with conn.cursor() as cur:
                await cur.execute(_SELECT_BY_ID, (task_id,))
                row = await cur.fetchone()
        return _row_to_task(row) if row is not None else None

    async def list_all(self) -> list[ScheduledTask]:
        """Retorna todas as tarefas, sem filtro (uso admin — REQ-008)."""
        async with await psycopg.AsyncConnection.connect(self._conninfo) as conn:
            async with conn.cursor() as cur:
                await cur.execute(_SELECT_ALL)
                rows = await cur.fetchall()
        return [_row_to_task(row) for row in rows]

    async def list_by_owner(self, owner_user_key: str) -> list[ScheduledTask]:
        """Retorna as tarefas cujo `owner_user_key` corresponde (REQ-008)."""
        async with await psycopg.AsyncConnection.connect(self._conninfo) as conn:
            async with conn.cursor() as cur:
                await cur.execute(_SELECT_BY_OWNER, (owner_user_key,))
                rows = await cur.fetchall()
        return [_row_to_task(row) for row in rows]

    async def delete(self, task_id: str) -> None:
        """Remove a tarefa; tolerante a `task_id` inexistente (no-op)."""
        async with await psycopg.AsyncConnection.connect(self._conninfo) as conn:
            async with conn.cursor() as cur:
                await cur.execute(_DELETE, (task_id,))
            await conn.commit()


def _row_to_task(row: tuple[Any, ...]) -> ScheduledTask:
    (
        id_,
        prompt,
        thread_id,
        owner_user_key,
        delivery_user_key,
        skills,
        tool_scope,
        schedule_kind,
        schedule_expr,
        status,
        timeout_seconds,
        started_at,
        finished_at,
        last_error,
        created_at,
    ) = row
    return ScheduledTask(
        id=id_,
        prompt=prompt,
        thread_id=thread_id,
        schedule=Schedule(kind=schedule_kind, expr=schedule_expr),
        owner_user_key=owner_user_key,
        delivery_user_key=delivery_user_key,
        tool_scope=ToolScope(tool_scope),
        skills=tuple(skills),
        timeout_seconds=timeout_seconds,
        status=TaskStatus(status),
        started_at=started_at,
        finished_at=finished_at,
        error=last_error,
        created_at=created_at,
    )
