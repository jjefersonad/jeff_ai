"""Fire-time de `ScheduledTask.profile_id` (sched-2 / REQ-008, REQ-015)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.ports.agent_runner import AgentRunnerPort, AgentRunResult
from src.application.ports.scheduled_task_repository import ScheduledTaskRepositoryPort
from src.application.use_cases.run_scheduled_task import RunScheduledTask
from src.domain.scheduling import Schedule, ScheduledTask, TaskStatus, ToolScope
from src.infrastructure.channels.scheduled_channel import ScheduledChannel


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


class _RecordingRunner(AgentRunnerPort):
    def __init__(self, *, result: AgentRunResult | None = None) -> None:
        self._result = result or AgentRunResult(thread_id="th-1", status="ok")
        self.calls: list[dict] = []

    async def run(
        self,
        *,
        thread_id: str,
        prompt: str,
        skills: tuple[str, ...],
        tool_scope: ToolScope,
        user_key: str | None = None,
        profile_id: str | None = None,
        use_default_profile: bool = False,
    ) -> AgentRunResult:
        self.calls.append(
            {
                "thread_id": thread_id,
                "prompt": prompt,
                "skills": skills,
                "tool_scope": tool_scope,
                "user_key": user_key,
                "profile_id": profile_id,
                "use_default_profile": use_default_profile,
            }
        )
        return self._result

    async def resume(
        self,
        *,
        thread_id: str,
        decisions: tuple[dict, ...],
        user_key: str | None = None,
    ) -> AgentRunResult:
        raise NotImplementedError


def _make_use_case(
    *,
    repository: ScheduledTaskRepositoryPort,
    agent_runner: AgentRunnerPort,
) -> RunScheduledTask:
    notifier = MagicMock()
    notifier.execute = AsyncMock()
    return RunScheduledTask(
        repository=repository,
        agent_runner=agent_runner,
        handle_chat_message=notifier,
        notify_channel=ScheduledChannel(),
    )


def _make_task(**overrides: object) -> ScheduledTask:
    kwargs: dict[str, object] = {
        "id": "t-1",
        "prompt": "faz o resumo diário",
        "thread_id": "th-1",
        "schedule": Schedule(kind="once", expr="2026-01-01T00:00:00"),
        "owner_user_key": "web:owner-1",
        "timeout_seconds": 60,
    }
    kwargs.update(overrides)
    return ScheduledTask(**kwargs)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_execute_passes_profile_id_to_agent_runner() -> None:
    """WHEN the due task has a valid profile_id THEN agent_runner.run receives it."""
    repo = _FakeRepository()
    await repo.save(_make_task(profile_id="p-coder"))
    runner = _RecordingRunner()
    use_case = _make_use_case(repository=repo, agent_runner=runner)

    await use_case.execute(task_id="t-1")

    assert len(runner.calls) == 1
    call = runner.calls[0]
    assert call["profile_id"] == "p-coder"
    assert call["user_key"] == "web:owner-1"
    assert call["use_default_profile"] is False
    stored = await repo.get("t-1")
    assert stored is not None
    assert stored.status == TaskStatus.SUCCEEDED


@pytest.mark.asyncio
async def test_null_profile_id_is_no_op_overlay() -> None:
    """WHEN profile_id is null THEN run is overlay no-op (not get_default)."""
    repo = _FakeRepository()
    await repo.save(_make_task(profile_id=None))
    runner = _RecordingRunner()
    use_case = _make_use_case(repository=repo, agent_runner=runner)

    await use_case.execute(task_id="t-1")

    call = runner.calls[0]
    assert call["profile_id"] is None
    assert call["use_default_profile"] is False


@pytest.mark.asyncio
async def test_archived_profile_at_fire_marks_task_failed() -> None:
    """WHEN the runner refuses an archived profile THEN the task is FAILED."""
    repo = _FakeRepository()
    await repo.save(_make_task(profile_id="p-archived"))
    runner = _RecordingRunner(
        result=AgentRunResult(
            thread_id="th-1",
            status="error",
            error="profile_id inválido",
        )
    )
    use_case = _make_use_case(repository=repo, agent_runner=runner)

    await use_case.execute(task_id="t-1")

    stored = await repo.get("t-1")
    assert stored is not None
    assert stored.status == TaskStatus.FAILED
    assert stored.error is not None
    assert "profile_id" in stored.error
    assert runner.calls[0]["use_default_profile"] is False
