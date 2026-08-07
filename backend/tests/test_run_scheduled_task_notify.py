"""Testes de notificação em `RunScheduledTask` (task
`unify-message-delivery-pipeline-task-scheduled-1`).

Cobre REQ-009 / REQ-011 (scheduled-tasks): save-then-notify, skip quando
`output` ausente, e falha de notify best-effort (task permanece succeeded).
"""
from __future__ import annotations

import logging
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.ports.agent_runner import (
    AgentRunnerPort,
    AgentRunOutcome,
    AgentRunResult,
)
from src.application.ports.scheduled_task_repository import ScheduledTaskRepositoryPort
from src.application.use_cases.run_scheduled_task import RunScheduledTask
from src.domain.scheduling import Schedule, ScheduledTask, TaskStatus, ToolScope
from src.infrastructure.channels.scheduled_channel import ScheduledChannel


class _FakeRepository(ScheduledTaskRepositoryPort):
    def __init__(self, *, call_log: list[str] | None = None) -> None:
        self._store: dict[str, ScheduledTask] = {}
        self._call_log = call_log

    async def save(self, task: ScheduledTask) -> None:
        if self._call_log is not None:
            self._call_log.append(f"save:{task.status.value}")
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
    def __init__(self, *, result: AgentRunResult) -> None:
        self._result = result

    async def run(
        self,
        *,
        thread_id: str,
        prompt: str,
        skills: tuple[str, ...],
        tool_scope: ToolScope,
        user_key: str | None = None,
    ) -> AgentRunResult:
        return self._result

    async def resume(
        self,
        *,
        thread_id: str,
        decisions: tuple[dict, ...],
        user_key: str | None = None,
    ) -> AgentRunResult:
        raise NotImplementedError


def _make_task(**overrides: Any) -> ScheduledTask:
    kwargs: dict[str, Any] = {
        "id": "t-1",
        "prompt": "faz o resumo diário",
        "thread_id": "th-1",
        "schedule": Schedule(kind="once", expr="2026-01-01T00:00:00"),
        "owner_user_key": "telegram:1234",
        "timeout_seconds": 60,
    }
    kwargs.update(overrides)
    return ScheduledTask(**kwargs)


def _make_notifier(*, call_log: list[str], raises: Exception | None = None) -> MagicMock:
    notifier = MagicMock()

    async def _execute(**kwargs: Any) -> None:
        call_log.append("notify")
        if raises is not None:
            raise raises

    notifier.execute = AsyncMock(side_effect=_execute)
    return notifier


@pytest.mark.asyncio
async def test_save_then_notify_on_success_with_output() -> None:
    """Unit-1: `repo.save(succeeded)` ANTES de `HandleChatMessage.execute`."""
    call_log: list[str] = []
    repo = _FakeRepository(call_log=call_log)
    task = _make_task()
    await repo.save(task)
    call_log.clear()

    outcome = AgentRunOutcome(text="Resultado do job", attachments=())
    runner = _RecordingRunner(
        result=AgentRunResult(thread_id="th-1", status="ok", output=outcome)
    )
    channel = ScheduledChannel()
    notifier = _make_notifier(call_log=call_log)
    use_case = RunScheduledTask(
        repository=repo,
        agent_runner=runner,
        handle_chat_message=notifier,
        notify_channel=channel,
    )

    await use_case.execute(task_id="t-1")

    assert call_log == ["save:succeeded", "notify"]
    notifier.execute.assert_awaited_once()
    kwargs = notifier.execute.await_args.kwargs
    assert isinstance(kwargs["channel"], ScheduledChannel)
    assert kwargs["channel"] is channel
    assert kwargs["user_key"] == "telegram:1234"
    assert kwargs["thread_id"] == "th-1"
    assert kwargs["text"] == "Resultado do job"

    stored = await repo.get("t-1")
    assert stored is not None
    assert stored.status == TaskStatus.SUCCEEDED


@pytest.mark.asyncio
async def test_skips_notify_when_output_missing(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Unit-2: status=ok sem output → WARNING scheduled_notify_skipped; sem notify."""
    call_log: list[str] = []
    repo = _FakeRepository(call_log=call_log)
    await repo.save(_make_task())
    call_log.clear()

    runner = _RecordingRunner(
        result=AgentRunResult(thread_id="th-1", status="ok", output=None)
    )
    notifier = _make_notifier(call_log=call_log)
    use_case = RunScheduledTask(
        repository=repo,
        agent_runner=runner,
        handle_chat_message=notifier,
        notify_channel=ScheduledChannel(),
    )

    with caplog.at_level(logging.WARNING):
        await use_case.execute(task_id="t-1")

    assert "notify" not in call_log
    notifier.execute.assert_not_awaited()
    assert any(
        "scheduled_notify_skipped" in r.message and "output_missing" in r.message
        for r in caplog.records
        if r.levelno == logging.WARNING
    )


@pytest.mark.asyncio
async def test_notify_failure_keeps_task_succeeded(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Unit-3: notify levanta → engole, ERROR scheduled_notify_failed, status=succeeded."""
    call_log: list[str] = []
    repo = _FakeRepository(call_log=call_log)
    await repo.save(_make_task())
    call_log.clear()

    outcome = AgentRunOutcome(text="ok", attachments=())
    runner = _RecordingRunner(
        result=AgentRunResult(thread_id="th-1", status="ok", output=outcome)
    )
    notifier = _make_notifier(
        call_log=call_log, raises=RuntimeError("canal original não disponível")
    )
    use_case = RunScheduledTask(
        repository=repo,
        agent_runner=runner,
        handle_chat_message=notifier,
        notify_channel=ScheduledChannel(),
    )

    with caplog.at_level(logging.ERROR):
        await use_case.execute(task_id="t-1")

    assert call_log == ["save:succeeded", "notify"]
    stored = await repo.get("t-1")
    assert stored is not None
    assert stored.status == TaskStatus.SUCCEEDED
    assert any(
        "scheduled_notify_failed" in r.message for r in caplog.records if r.levelno == logging.ERROR
    )


@pytest.mark.asyncio
async def test_error_status_does_not_notify() -> None:
    """REQ-009: status=error → failed, sem HandleChatMessage."""
    call_log: list[str] = []
    repo = _FakeRepository(call_log=call_log)
    await repo.save(_make_task())
    call_log.clear()

    runner = _RecordingRunner(
        result=AgentRunResult(thread_id="th-1", status="error", error="boom")
    )
    notifier = _make_notifier(call_log=call_log)
    use_case = RunScheduledTask(
        repository=repo,
        agent_runner=runner,
        handle_chat_message=notifier,
        notify_channel=ScheduledChannel(),
    )

    await use_case.execute(task_id="t-1")

    assert call_log == ["save:failed"]
    notifier.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_notify_uses_effective_delivery_user_key() -> None:
    """run-1 unit-1: sucesso notifica com delivery_user_key, não owner web."""
    call_log: list[str] = []
    repo = _FakeRepository(call_log=call_log)
    await repo.save(
        _make_task(
            owner_user_key="web:1",
            delivery_user_key="whatsapp:9",
        )
    )
    call_log.clear()

    outcome = AgentRunOutcome(text="ok no zap", attachments=())
    runner = _RecordingRunner(
        result=AgentRunResult(thread_id="th-1", status="ok", output=outcome)
    )
    notifier = _make_notifier(call_log=call_log)
    use_case = RunScheduledTask(
        repository=repo,
        agent_runner=runner,
        handle_chat_message=notifier,
        notify_channel=ScheduledChannel(),
    )

    await use_case.execute(task_id="t-1")

    notifier.execute.assert_awaited_once()
    kwargs = notifier.execute.await_args.kwargs
    assert kwargs["user_key"] == "whatsapp:9"
    assert kwargs["text"] == "ok no zap"
