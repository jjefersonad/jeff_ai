"""Testes unitários do entrypoint `src/infrastructure/cli/jeff_cli.py`
(task `agendamento-jeff-cli-task-runtime-2`).

Cobre:
- `parse_args`: exige `--job-id`.
- `main()`: falha rápido (exit 1) e NÃO monta o composition root quando
  `POSTGRES_URI` está ausente (jeff-cli REQ-001: sem estado/efeito colateral
  se a configuração estiver incompleta).
- `_run()`: traduz o status final da tarefa em exit code (jeff-cli REQ-004)
  — SUCCEEDED/inexistente → 0, qualquer outro status → != 0 — usando fakes
  injetados via `_build_components` (Humble Object: `jeff_cli.py` não
  decide nada, só chama `RunScheduledTask.execute` e lê o resultado).

O teste de processo real (subprocesso de ponta a ponta contra Postgres) é
`test_jeff_cli_subprocess.py`, gated por `INTEGRATION_POSTGRES_URI`.
"""
from __future__ import annotations

import pytest

from unittest.mock import AsyncMock, MagicMock

from src.application.ports.agent_runner import AgentRunnerPort, AgentRunResult
from src.application.ports.scheduled_task_repository import ScheduledTaskRepositoryPort
from src.application.use_cases.run_scheduled_task import RunScheduledTask
from src.domain.scheduling import Schedule, ScheduledTask, ToolScope
from src.infrastructure.channels.registry import ChannelRegistry
from src.infrastructure.channels.scheduled_channel import ScheduledChannel
from src.infrastructure.cli import jeff_cli


@pytest.fixture(autouse=True)
def _isolated_registry():
    ChannelRegistry.reset()
    yield
    ChannelRegistry.reset()


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
    def __init__(self, *, status: str, error: str | None = None) -> None:
        self._status = status
        self._error = error

    async def run(
        self,
        *,
        thread_id: str,
        prompt: str,
        skills: tuple[str, ...],
        tool_scope: ToolScope,
        user_key: str | None = None,
    ) -> AgentRunResult:
        return AgentRunResult(thread_id=thread_id, status=self._status, error=self._error)

    async def resume(
        self,
        *,
        thread_id: str,
        decisions: tuple[dict, ...],
        user_key: str | None = None,
    ) -> AgentRunResult:
        raise NotImplementedError


def _make_task(**overrides: object) -> ScheduledTask:
    kwargs: dict[str, object] = {
        "id": "job-1",
        "prompt": "diga oi",
        "thread_id": "th-1",
        "schedule": Schedule(kind="once", expr="2026-01-01T00:00:00"),
        "owner_user_key": "web:owner-1",
    }
    kwargs.update(overrides)
    return ScheduledTask(**kwargs)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# parse_args
# ---------------------------------------------------------------------------


def test_parse_args_requires_job_id():
    with pytest.raises(SystemExit):
        jeff_cli.parse_args([])


def test_parse_args_reads_job_id():
    args = jeff_cli.parse_args(["--job-id", "abc-123"])
    assert args.job_id == "abc-123"


# ---------------------------------------------------------------------------
# main() — falha rápido sem POSTGRES_URI, sem montar composition root
# ---------------------------------------------------------------------------


def test_main_returns_1_and_skips_wiring_when_postgres_uri_missing(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.delenv("POSTGRES_URI", raising=False)
    # main() chama load_env() — sem isso, backend/.env / ./.env reporiam a var.
    monkeypatch.setattr(jeff_cli, "load_env", lambda: None)
    called = False

    def _fail_if_called(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("não deveria montar o composition root sem POSTGRES_URI")

    monkeypatch.setattr(jeff_cli, "_build_components", _fail_if_called)
    monkeypatch.setattr(jeff_cli, "_register_channels", _fail_if_called)

    exit_code = jeff_cli.main(["--job-id", "job-1"])

    assert exit_code == 1
    assert called is False


def test_main_returns_run_result_when_postgres_uri_present(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("POSTGRES_URI", "postgresql://fake/db")
    monkeypatch.setattr(jeff_cli, "load_env", lambda: None)
    repo = _FakeRepository()
    task = _make_task()
    import asyncio

    asyncio.run(repo.save(task))
    monkeypatch.setattr(
        jeff_cli,
        "_build_components",
        lambda postgres_uri: (
            repo,
            _make_run_scheduled_task(
                repository=repo, agent_runner=_FakeRunner(status="ok")
            ),
        ),
    )

    exit_code = jeff_cli.main(["--job-id", "job-1"])

    assert exit_code == 0


# ---------------------------------------------------------------------------
# _run() — status final da tarefa vira exit code (REQ-004)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_returns_0_when_task_succeeds():
    repo = _FakeRepository()
    await repo.save(_make_task())
    use_case = _make_run_scheduled_task(
        repository=repo, agent_runner=_FakeRunner(status="ok")
    )

    exit_code = await jeff_cli._run(
        job_id="job-1", components=(repo, use_case)
    )

    assert exit_code == 0


@pytest.mark.asyncio
async def test_run_returns_nonzero_when_task_fails():
    repo = _FakeRepository()
    await repo.save(_make_task())
    use_case = _make_run_scheduled_task(
        repository=repo, agent_runner=_FakeRunner(status="error", error="boom")
    )

    exit_code = await jeff_cli._run(
        job_id="job-1", components=(repo, use_case)
    )

    assert exit_code != 0


@pytest.mark.asyncio
async def test_run_returns_0_when_task_no_longer_exists():
    """Tarefa cancelada entre agendamento e disparo: no-op tolerante (exit 0)."""
    repo = _FakeRepository()
    use_case = _make_run_scheduled_task(
        repository=repo, agent_runner=_FakeRunner(status="ok")
    )

    exit_code = await jeff_cli._run(
        job_id="does-not-exist", components=(repo, use_case)
    )

    assert exit_code == 0
