"""Testes do composition root de canais no `jeff_cli` (task
`unify-message-delivery-pipeline-task-composition-2`).

Cobre REQ-002 scenario 2 (chat-channel-port): `jeff_cli.main()` registra
apenas `ScheduledChannel` — `ChannelRegistry.get(TELEGRAM)` etc. ainda
levantam `RuntimeError` neste processo.
"""
from __future__ import annotations

import pytest

from unittest.mock import AsyncMock, MagicMock

from src.application.ports.agent_runner import AgentRunnerPort, AgentRunResult
from src.application.ports.scheduled_task_repository import ScheduledTaskRepositoryPort
from src.application.use_cases.run_scheduled_task import RunScheduledTask
from src.domain.channels import ChannelKind
from src.domain.scheduling import Schedule, ScheduledTask, ToolScope
from src.infrastructure.channels.registry import ChannelRegistry
from src.infrastructure.channels.scheduled_channel import ScheduledChannel
from src.infrastructure.cli import jeff_cli


def _make_run_scheduled_task(
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


class _FakeRunner(AgentRunnerPort):
    async def run(
        self,
        *,
        thread_id: str,
        prompt: str,
        skills: tuple[str, ...],
        tool_scope: ToolScope,
        user_key: str | None = None,
    ) -> AgentRunResult:
        return AgentRunResult(thread_id=thread_id, status="ok")

    async def resume(
        self,
        *,
        thread_id: str,
        decisions: tuple[dict, ...],
        user_key: str | None = None,
    ) -> AgentRunResult:
        raise NotImplementedError


@pytest.fixture(autouse=True)
def _isolated_registry():
    ChannelRegistry.reset()
    yield
    ChannelRegistry.reset()


def test_jeff_cli_main_registers_only_scheduled_channel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REQ-002 scenario 2: subprocess agendado só registra ScheduledChannel."""
    monkeypatch.setenv("POSTGRES_URI", "postgresql://fake/db")
    monkeypatch.setattr(jeff_cli, "load_env", lambda: None)

    repo = _FakeRepository()
    task = ScheduledTask(
        id="job-1",
        prompt="diga oi",
        thread_id="th-1",
        schedule=Schedule(kind="once", expr="2026-01-01T00:00:00"),
        owner_user_key="web:owner-1",
    )
    import asyncio

    asyncio.run(repo.save(task))
    monkeypatch.setattr(
        jeff_cli,
        "_build_components",
        lambda postgres_uri: (
            repo,
            _make_run_scheduled_task(repository=repo, agent_runner=_FakeRunner()),
        ),
    )

    exit_code = jeff_cli.main(["--job-id", "job-1"])

    assert exit_code == 0
    assert isinstance(ChannelRegistry.get(ChannelKind.SCHEDULED), ScheduledChannel)
    with pytest.raises(RuntimeError, match="telegram"):
        ChannelRegistry.get(ChannelKind.TELEGRAM)
    with pytest.raises(RuntimeError, match="whatsapp"):
        ChannelRegistry.get(ChannelKind.WHATSAPP)
    with pytest.raises(RuntimeError, match="web"):
        ChannelRegistry.get(ChannelKind.WEB)
