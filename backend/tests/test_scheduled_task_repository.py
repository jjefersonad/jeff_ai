"""Teste de integração: `PostgresScheduledTaskRepository` (task
`agendamento-jeff-cli-task-persistence-2`).

Cobre os critérios de aceite da task:
- save/get/list_all/list_by_owner/delete operam contra a tabela real `scheduled_tasks`
- get(task_id) retorna None (nunca exceção) para id inexistente
- list_by_owner filtra por owner_user_key; list_all (admin) não filtra

Requer `INTEGRATION_POSTGRES_URI` apontando para um Postgres real — mesmo
padrão de `test_langgraph_direct_runner.py`.
"""
from __future__ import annotations

import os
import uuid

import pytest

from src.domain.scheduling import Schedule, ScheduledTask, TaskStatus, ToolScope
from src.infrastructure.persistence.scheduled_tasks_schema import ensure_schema

INTEGRATION_URI_ENV = "INTEGRATION_POSTGRES_URI"
pytestmark = pytest.mark.skipif(
    not os.environ.get(INTEGRATION_URI_ENV),
    reason=(
        f"Requer Postgres de teste real. Defina {INTEGRATION_URI_ENV} "
        "(ex.: postgresql://jeff_ia:jeff_ia@localhost:5436/jeff_ia) "
        "para rodar este teste."
    ),
)


def _uri() -> str:
    return os.environ[INTEGRATION_URI_ENV]


@pytest.fixture(autouse=True)
def _ensure_table() -> None:
    ensure_schema(_uri())


def _new_task(**overrides: object) -> ScheduledTask:
    kwargs: dict[str, object] = {
        "id": str(uuid.uuid4()),
        "prompt": "diga olá",
        "thread_id": "th-1",
        "schedule": Schedule(kind="once", expr="2026-12-31T23:59:00"),
        "owner_user_key": "web:owner-1",
    }
    kwargs.update(overrides)
    return ScheduledTask(**kwargs)  # type: ignore[arg-type]


async def test_get_missing_task_returns_none_without_raising() -> None:
    from src.infrastructure.persistence.scheduled_task_repository import (
        PostgresScheduledTaskRepository,
    )

    repo = PostgresScheduledTaskRepository(_uri())

    assert await repo.get(str(uuid.uuid4())) is None


async def test_save_then_get_round_trips_all_fields() -> None:
    from src.infrastructure.persistence.scheduled_task_repository import (
        PostgresScheduledTaskRepository,
    )

    repo = PostgresScheduledTaskRepository(_uri())
    task = _new_task(
        skills=("brand-guidelines", "canvas-design"),
        tool_scope=ToolScope.FULL,
        timeout_seconds=120,
    )

    await repo.save(task)
    fetched = await repo.get(task.id)

    assert fetched is not None
    assert fetched.id == task.id
    assert fetched.prompt == task.prompt
    assert fetched.thread_id == task.thread_id
    assert fetched.owner_user_key == task.owner_user_key
    assert fetched.schedule == task.schedule
    assert fetched.tool_scope == ToolScope.FULL
    assert fetched.skills == ("brand-guidelines", "canvas-design")
    assert fetched.timeout_seconds == 120
    assert fetched.status == TaskStatus.SCHEDULED


async def test_save_is_idempotent_upsert_on_id() -> None:
    from src.infrastructure.persistence.scheduled_task_repository import (
        PostgresScheduledTaskRepository,
    )

    repo = PostgresScheduledTaskRepository(_uri())
    task = _new_task()

    await repo.save(task)
    task.start()
    task.succeed()
    await repo.save(task)

    fetched = await repo.get(task.id)
    assert fetched is not None
    assert fetched.status == TaskStatus.SUCCEEDED
    assert fetched.started_at is not None
    assert fetched.finished_at is not None

    all_tasks = await repo.list_all()
    assert len([t for t in all_tasks if t.id == task.id]) == 1


async def test_save_persists_failure_error_message() -> None:
    from src.infrastructure.persistence.scheduled_task_repository import (
        PostgresScheduledTaskRepository,
    )

    repo = PostgresScheduledTaskRepository(_uri())
    task = _new_task()
    task.start()
    task.fail("boom")

    await repo.save(task)
    fetched = await repo.get(task.id)

    assert fetched is not None
    assert fetched.status == TaskStatus.FAILED
    assert fetched.error == "boom"


async def test_list_all_returns_tasks_from_every_owner() -> None:
    from src.infrastructure.persistence.scheduled_task_repository import (
        PostgresScheduledTaskRepository,
    )

    repo = PostgresScheduledTaskRepository(_uri())
    task_a = _new_task(owner_user_key="web:owner-A")
    task_b = _new_task(owner_user_key="web:owner-B")
    await repo.save(task_a)
    await repo.save(task_b)

    all_tasks = await repo.list_all()
    ids = {t.id for t in all_tasks}

    assert task_a.id in ids
    assert task_b.id in ids


async def test_list_by_owner_filters_to_matching_owner_only() -> None:
    from src.infrastructure.persistence.scheduled_task_repository import (
        PostgresScheduledTaskRepository,
    )

    repo = PostgresScheduledTaskRepository(_uri())
    owner_key = f"web:{uuid.uuid4()}"
    other_key = f"web:{uuid.uuid4()}"
    mine = _new_task(owner_user_key=owner_key)
    theirs = _new_task(owner_user_key=other_key)
    await repo.save(mine)
    await repo.save(theirs)

    only_mine = await repo.list_by_owner(owner_key)

    assert [t.id for t in only_mine] == [mine.id]


async def test_delete_removes_task() -> None:
    from src.infrastructure.persistence.scheduled_task_repository import (
        PostgresScheduledTaskRepository,
    )

    repo = PostgresScheduledTaskRepository(_uri())
    task = _new_task()
    await repo.save(task)

    await repo.delete(task.id)

    assert await repo.get(task.id) is None


async def test_delete_missing_task_is_noop() -> None:
    from src.infrastructure.persistence.scheduled_task_repository import (
        PostgresScheduledTaskRepository,
    )

    repo = PostgresScheduledTaskRepository(_uri())

    await repo.delete(str(uuid.uuid4()))  # não deve levantar exceção


async def test_ensure_schema_idempotent_and_round_trips_delivery_waiting_human() -> None:
    """schema-1 unit-1: ensure_schema ×2 + save/get com delivery_user_key e WAITING_HUMAN."""
    from src.infrastructure.persistence.scheduled_task_repository import (
        PostgresScheduledTaskRepository,
    )

    ensure_schema(_uri())
    ensure_schema(_uri())

    repo = PostgresScheduledTaskRepository(_uri())
    task = _new_task(delivery_user_key="whatsapp:5511999999999")
    task.start()
    task.waiting_human()

    await repo.save(task)
    fetched = await repo.get(task.id)

    assert fetched is not None
    assert fetched.delivery_user_key == "whatsapp:5511999999999"
    assert fetched.status == TaskStatus.WAITING_HUMAN
    assert fetched.effective_delivery_user_key == "whatsapp:5511999999999"
