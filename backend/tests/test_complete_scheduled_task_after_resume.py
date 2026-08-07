"""Testes de `CompleteScheduledTaskAfterResume` (resume-1).

Cobre:
- unit-1: approve/sucesso → SUCCEEDED (cron → SCHEDULED)
- unit-2: reject → FAILED (cron → SCHEDULED)
- unit-3: thread sem WAITING_HUMAN → no-op sem save
"""
from __future__ import annotations

import pytest

from src.application.ports.scheduled_task_repository import ScheduledTaskRepositoryPort
from src.application.use_cases.complete_scheduled_task_after_resume import (
    CompleteScheduledTaskAfterResume,
)
from src.domain.scheduling import Schedule, ScheduledTask, TaskStatus, ToolScope


class _FakeRepository(ScheduledTaskRepositoryPort):
    def __init__(self) -> None:
        self._store: dict[str, ScheduledTask] = {}
        self.save_calls: list[str] = []

    async def save(self, task: ScheduledTask) -> None:
        self.save_calls.append(task.id)
        self._store[task.id] = task

    async def get(self, task_id: str) -> ScheduledTask | None:
        return self._store.get(task_id)

    async def list_all(self) -> list[ScheduledTask]:
        return list(self._store.values())

    async def list_by_owner(self, owner_user_key: str) -> list[ScheduledTask]:
        return [t for t in self._store.values() if t.owner_user_key == owner_user_key]

    async def delete(self, task_id: str) -> None:
        self._store.pop(task_id, None)


def _waiting_task(**overrides: object) -> ScheduledTask:
    kwargs: dict[str, object] = {
        "id": "t-1",
        "prompt": "rotina",
        "thread_id": "th-hitl",
        "schedule": Schedule(kind="once", expr="2026-01-01T00:00:00"),
        "owner_user_key": "web:1",
        "delivery_user_key": "whatsapp:9",
        "tool_scope": ToolScope.FULL,
    }
    kwargs.update(overrides)
    task = ScheduledTask(**kwargs)  # type: ignore[arg-type]
    task.start()
    task.waiting_human()
    return task


@pytest.mark.asyncio
async def test_resume_succeed_completes_once_to_succeeded():
    """unit-1 (once): sucesso → SUCCEEDED."""
    repo = _FakeRepository()
    await repo.save(_waiting_task())
    repo.save_calls.clear()

    result = await CompleteScheduledTaskAfterResume(repository=repo).execute(
        thread_id="th-hitl",
        outcome="succeeded",
    )

    assert result is not None
    assert result.status == TaskStatus.SUCCEEDED
    assert repo.save_calls == ["t-1"]
    stored = await repo.get("t-1")
    assert stored is not None
    assert stored.status == TaskStatus.SUCCEEDED


@pytest.mark.asyncio
async def test_resume_succeed_cron_rearms_to_scheduled():
    """unit-1 (cron): sucesso → rearme SCHEDULED, mesmo thread_id."""
    repo = _FakeRepository()
    await repo.save(
        _waiting_task(schedule=Schedule(kind="cron", expr="0 9 * * *"))
    )
    repo.save_calls.clear()

    result = await CompleteScheduledTaskAfterResume(repository=repo).execute(
        thread_id="th-hitl",
        outcome="succeeded",
    )

    assert result is not None
    assert result.status == TaskStatus.SCHEDULED
    assert result.thread_id == "th-hitl"


@pytest.mark.asyncio
async def test_resume_reject_marks_failed_once():
    """unit-2 (once): reject → FAILED."""
    repo = _FakeRepository()
    await repo.save(_waiting_task())
    repo.save_calls.clear()

    result = await CompleteScheduledTaskAfterResume(repository=repo).execute(
        thread_id="th-hitl",
        outcome="failed",
        error="usuário rejeitou",
    )

    assert result is not None
    assert result.status == TaskStatus.FAILED
    assert result.error == "usuário rejeitou"
    assert result.status is not TaskStatus.WAITING_HUMAN


@pytest.mark.asyncio
async def test_resume_reject_cron_rearms_to_scheduled():
    """unit-2 (cron): reject → FAILED depois rearme SCHEDULED."""
    repo = _FakeRepository()
    await repo.save(
        _waiting_task(schedule=Schedule(kind="cron", expr="0 9 * * *"))
    )
    repo.save_calls.clear()

    result = await CompleteScheduledTaskAfterResume(repository=repo).execute(
        thread_id="th-hitl",
        outcome="failed",
        error="reject",
    )

    assert result is not None
    assert result.status == TaskStatus.SCHEDULED
    assert result.error is None


@pytest.mark.asyncio
async def test_resume_without_waiting_task_is_noop():
    """unit-3: sem WAITING_HUMAN → None, sem save."""
    repo = _FakeRepository()
    # tarefa em outro estado
    task = ScheduledTask(
        id="t-ok",
        prompt="x",
        thread_id="th-other",
        schedule=Schedule(kind="once", expr="2026-01-01T00:00:00"),
    )
    await repo.save(task)
    repo.save_calls.clear()

    result = await CompleteScheduledTaskAfterResume(repository=repo).execute(
        thread_id="th-hitl",
        outcome="succeeded",
    )

    assert result is None
    assert repo.save_calls == []
