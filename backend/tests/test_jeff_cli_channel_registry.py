"""Testes do composition root de canais no `jeff_cli`
(scheduled-channel-routines-task-cli-1).

Cobre REQ-005 (scheduled-delivery-targeting): com env de Telegram/WhatsApp,
`ChannelRegistry` resolve esses canais; `SCHEDULED` e `WEB` sempre; sem
credenciais o boot não quebra.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.ports.agent_runner import AgentRunnerPort, AgentRunResult
from src.application.ports.scheduled_task_repository import ScheduledTaskRepositoryPort
from src.application.use_cases.run_scheduled_task import RunScheduledTask
from src.domain.channels import ChannelKind
from src.domain.scheduling import Schedule, ScheduledTask, ToolScope
from src.infrastructure.channels.registry import ChannelRegistry
from src.infrastructure.channels.scheduled_channel import ScheduledChannel
from src.infrastructure.channels.telegram_channel import TelegramChannel
from src.infrastructure.channels.web_channel import WebChannel
from src.infrastructure.channels.whatsapp_channel import WhatsAppChannel
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


def _stub_main_deps(monkeypatch: pytest.MonkeyPatch) -> _FakeRepository:
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
    asyncio.run(repo.save(task))
    monkeypatch.setattr(
        jeff_cli,
        "_build_components",
        lambda postgres_uri: (
            repo,
            _make_run_scheduled_task(repository=repo, agent_runner=_FakeRunner()),
        ),
    )
    return repo


def test_jeff_cli_main_registers_telegram_and_whatsapp_when_env_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """cli-1 unit-1 / REQ-005: com env, get(WHATSAPP)/get(TELEGRAM) não levantam."""
    _stub_main_deps(monkeypatch)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:ABC-DEF")
    monkeypatch.setenv("EVOLUTION_INSTANCE_NAME", "jeff-wa")

    exit_code = jeff_cli.main(["--job-id", "job-1"])

    assert exit_code == 0
    assert isinstance(ChannelRegistry.get(ChannelKind.SCHEDULED), ScheduledChannel)
    assert isinstance(ChannelRegistry.get(ChannelKind.WEB), WebChannel)
    assert isinstance(ChannelRegistry.get(ChannelKind.TELEGRAM), TelegramChannel)
    assert isinstance(ChannelRegistry.get(ChannelKind.WHATSAPP), WhatsAppChannel)


def test_jeff_cli_main_boots_without_channel_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sem credenciais: boot ok; SCHEDULED+WEB presentes; TG/WA ausentes."""
    _stub_main_deps(monkeypatch)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("EVOLUTION_INSTANCE_NAME", raising=False)

    exit_code = jeff_cli.main(["--job-id", "job-1"])

    assert exit_code == 0
    assert isinstance(ChannelRegistry.get(ChannelKind.SCHEDULED), ScheduledChannel)
    assert isinstance(ChannelRegistry.get(ChannelKind.WEB), WebChannel)
    with pytest.raises(RuntimeError, match="telegram"):
        ChannelRegistry.get(ChannelKind.TELEGRAM)
    with pytest.raises(RuntimeError, match="whatsapp"):
        ChannelRegistry.get(ChannelKind.WHATSAPP)
