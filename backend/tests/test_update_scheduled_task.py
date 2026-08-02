"""Testes do use case `UpdateScheduledTask` (task `agendamento-jeff-cli-frontend-task-application-1`).

Puro: usa fakes das portas. Verifica REQ-009 do delta `task-scheduling`:
- Cenário 1: dono edita a própria tarefa SCHEDULED → campos persistidos via
  `repo.save()`; se `schedule` mudou, `scheduler.unschedule()` + `scheduler.schedule()`
  re-registram o trigger.
- Cenário 2: não-dono/não-admin → `ScheduledTaskAuthorizationError`, tarefa inalterada.
- Cenário 3: `task.status != SCHEDULED` → edição rejeitada, tarefa inalterada.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.application.ports.scheduled_task_repository import ScheduledTaskRepositoryPort
from src.application.ports.task_scheduler import TaskSchedulerPort
from src.application.use_cases.cancel_scheduled_task import ScheduledTaskAuthorizationError
from src.application.use_cases.update_scheduled_task import (
    ScheduledTaskNotEditableError,
    UpdateScheduledTask,
)
from src.domain.scheduling import Schedule, ScheduledTask, TaskStatus, ToolScope

# ---------------------------------------------------------------------------
# Fakes locais
# ---------------------------------------------------------------------------


class _FakeRepository(ScheduledTaskRepositoryPort):
    def __init__(self) -> None:
        self._store: dict[str, ScheduledTask] = {}

    async def save(self, task: ScheduledTask) -> None:
        self._store[task.id] = task

    async def get(self, task_id: str) -> ScheduledTask | None:
        return self._store.get(task_id)

    async def list_all(self) -> list[ScheduledTask]:
        return list(self._store.values())

    async def list_by_owner(self, owner_user_key: str) -> list[ScheduledTask]:
        return [t for t in self._store.values() if t.owner_user_key == owner_user_key]

    async def delete(self, task_id: str) -> None:
        self._store.pop(task_id, None)


class _FakeScheduler(TaskSchedulerPort):
    def __init__(self) -> None:
        self.scheduled: list[str] = []
        self.unscheduled: list[str] = []

    async def schedule(self, task: ScheduledTask) -> None:
        self.scheduled.append(task.id)

    async def unschedule(self, task_id: str) -> None:
        self.unscheduled.append(task_id)


def _new_task(**overrides: object) -> ScheduledTask:
    defaults: dict[object, object] = dict(
        id="t-1",
        prompt="olá",
        thread_id="th-1",
        schedule=Schedule(kind="once", expr="2026-01-01T00:00:00"),
        owner_user_key="web:owner-1",
        tool_scope=ToolScope.RESTRICTED,
    )
    defaults.update(overrides)
    return ScheduledTask(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Unit 1 — dono edita tarefa SCHEDULED
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_updates_fields_and_reschedules_when_schedule_changes():
    repo = _FakeRepository()
    sched = _FakeScheduler()
    await repo.save(_new_task())
    use_case = UpdateScheduledTask(repository=repo, scheduler=sched)

    new_schedule = Schedule(kind="once", expr="2026-06-15T10:00:00")
    returned = await use_case.execute(
        task_id="t-1",
        caller_user_key="web:owner-1",
        is_admin=False,
        prompt="novo prompt",
        schedule=new_schedule,
    )

    assert returned.prompt == "novo prompt"
    assert returned.schedule == new_schedule

    stored = await repo.get("t-1")
    assert stored is not None
    assert stored.prompt == "novo prompt"
    assert stored.schedule == new_schedule

    assert sched.unscheduled == ["t-1"]
    assert sched.scheduled == ["t-1"]


@pytest.mark.asyncio
async def test_execute_does_not_reschedule_when_schedule_unchanged():
    repo = _FakeRepository()
    sched = _FakeScheduler()
    await repo.save(_new_task())
    use_case = UpdateScheduledTask(repository=repo, scheduler=sched)

    await use_case.execute(
        task_id="t-1",
        caller_user_key="web:owner-1",
        is_admin=False,
        prompt="só o prompt muda",
    )

    assert sched.unscheduled == []
    assert sched.scheduled == []


# ---------------------------------------------------------------------------
# Unit 2 — não-dono/não-admin
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_raises_when_caller_is_not_owner_and_not_admin():
    repo = _FakeRepository()
    sched = _FakeScheduler()
    await repo.save(_new_task())
    use_case = UpdateScheduledTask(repository=repo, scheduler=sched)

    with pytest.raises(ScheduledTaskAuthorizationError):
        await use_case.execute(
            task_id="t-1",
            caller_user_key="web:someone-else",
            is_admin=False,
            prompt="tentando editar",
        )

    stored = await repo.get("t-1")
    assert stored is not None
    assert stored.prompt == "olá"
    assert sched.scheduled == []
    assert sched.unscheduled == []


@pytest.mark.asyncio
async def test_execute_allows_admin_to_edit_others_task():
    repo = _FakeRepository()
    sched = _FakeScheduler()
    await repo.save(_new_task())
    use_case = UpdateScheduledTask(repository=repo, scheduler=sched)

    returned = await use_case.execute(
        task_id="t-1",
        caller_user_key="web:admin-1",
        is_admin=True,
        prompt="editado pelo admin",
    )

    assert returned.prompt == "editado pelo admin"


# ---------------------------------------------------------------------------
# Unit 3 — task.status != SCHEDULED
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [TaskStatus.RUNNING, TaskStatus.SUCCEEDED, TaskStatus.FAILED])
async def test_execute_rejects_edit_when_task_not_scheduled(status: TaskStatus):
    repo = _FakeRepository()
    sched = _FakeScheduler()
    task = _new_task()
    task.status = status
    await repo.save(task)
    use_case = UpdateScheduledTask(repository=repo, scheduler=sched)

    with pytest.raises(ScheduledTaskNotEditableError):
        await use_case.execute(
            task_id="t-1",
            caller_user_key="web:owner-1",
            is_admin=False,
            prompt="não deveria mudar",
        )

    stored = await repo.get("t-1")
    assert stored is not None
    assert stored.prompt == "olá"
    assert sched.scheduled == []
    assert sched.unscheduled == []


# ---------------------------------------------------------------------------
# Injeção de dependência
# ---------------------------------------------------------------------------


def test_constructor_stores_dependencies_by_injection():
    repo = _FakeRepository()
    sched = _FakeScheduler()
    use_case = UpdateScheduledTask(repository=repo, scheduler=sched)
    assert use_case._repository is repo
    assert use_case._scheduler is sched


def test_constructor_does_not_import_framework():
    """Garantia estática: o módulo não pode importar infra concreta."""
    src = (
        Path(__file__).parent.parent
        / "src"
        / "application"
        / "use_cases"
        / "update_scheduled_task.py"
    ).read_text()
    no_strings = re.sub(r'""".*?""""', "", src, flags=re.DOTALL)
    no_strings = re.sub(r"'''.*?'''", "", no_strings, flags=re.DOTALL)
    for forbidden in ("psycopg", "apscheduler", "langgraph", "fastapi"):
        assert not re.search(
            rf"^\s*(import|from)\s+{forbidden}\b", no_strings, flags=re.MULTILINE
        ), f"update_scheduled_task.py não pode importar {forbidden!r}"
