"""Testes do use case `RunScheduledTask` (task `agendamento-jeff-cli-task-application-4`).

Puro: usa fakes das portas. Verifica:
- REQ-002: `execute()` chama `task.start()` antes de invocar o agente e
  `task.succeed()`/`task.fail()` depois, respeitando a máquina de estado.
- REQ-006: `tool_scope` da tarefa é repassado ao `agent_runner.run(...)`.
- REQ-008: `owner_user_key` da tarefa é repassado como `user_key` ao runner.
- REQ-007: a chamada ao runner é envolvida por `timeout_seconds`; timeout
  excedido marca a tarefa FAILED com erro descritivo.
- `task_id` inexistente não levanta exceção não tratada (no-op tolerante).
"""
from __future__ import annotations

import asyncio
import re
from pathlib import Path

import pytest

from src.application.ports.agent_runner import AgentRunnerPort, AgentRunResult
from src.application.ports.scheduled_task_repository import ScheduledTaskRepositoryPort
from src.application.use_cases.run_scheduled_task import RunScheduledTask
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


class _RecordingRunner(AgentRunnerPort):
    """Registra os kwargs recebidos e devolve `result` (ou levanta `raises`)."""

    def __init__(self, *, result: AgentRunResult | None = None, raises: Exception | None = None) -> None:
        self._result = result
        self._raises = raises
        self.calls: list[dict] = []

    async def run(
        self,
        *,
        thread_id: str,
        prompt: str,
        skills: tuple[str, ...],
        tool_scope: ToolScope,
        user_key: str | None = None,
    ) -> AgentRunResult:
        self.calls.append(
            {
                "thread_id": thread_id,
                "prompt": prompt,
                "skills": skills,
                "tool_scope": tool_scope,
                "user_key": user_key,
            }
        )
        if self._raises is not None:
            raise self._raises
        assert self._result is not None
        return self._result

    async def resume(
        self,
        *,
        thread_id: str,
        decisions: tuple[dict, ...],
        user_key: str | None = None,
    ) -> AgentRunResult:
        raise NotImplementedError


class _HangingRunner(AgentRunnerPort):
    """Nunca retorna — usada para exercitar o timeout."""

    async def run(
        self,
        *,
        thread_id: str,
        prompt: str,
        skills: tuple[str, ...],
        tool_scope: ToolScope,
        user_key: str | None = None,
    ) -> AgentRunResult:
        await asyncio.sleep(3600)
        raise AssertionError("não deveria chegar aqui")

    async def resume(
        self,
        *,
        thread_id: str,
        decisions: tuple[dict, ...],
        user_key: str | None = None,
    ) -> AgentRunResult:
        raise NotImplementedError


def _make_task(**overrides) -> ScheduledTask:
    kwargs = {
        "id": "t-1",
        "prompt": "faz o resumo diário",
        "thread_id": "th-1",
        "schedule": Schedule(kind="once", expr="2026-01-01T00:00:00"),
        "owner_user_key": "web:owner-1",
        "timeout_seconds": 60,
    }
    kwargs.update(overrides)
    return ScheduledTask(**kwargs)


# ---------------------------------------------------------------------------
# REQ-002 — máquina de estado
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_marks_task_succeeded_on_ok_result():
    repo = _FakeRepository()
    task = _make_task()
    await repo.save(task)
    runner = _RecordingRunner(result=AgentRunResult(thread_id="th-1", status="ok"))
    use_case = RunScheduledTask(repository=repo, agent_runner=runner)

    await use_case.execute(task_id="t-1")

    stored = await repo.get("t-1")
    assert stored.status == TaskStatus.SUCCEEDED
    assert stored.error is None


@pytest.mark.asyncio
async def test_execute_marks_task_failed_on_agent_error_result():
    repo = _FakeRepository()
    task = _make_task()
    await repo.save(task)
    runner = _RecordingRunner(
        result=AgentRunResult(thread_id="th-1", status="error", error="boom")
    )
    use_case = RunScheduledTask(repository=repo, agent_runner=runner)

    await use_case.execute(task_id="t-1")

    stored = await repo.get("t-1")
    assert stored.status == TaskStatus.FAILED
    assert stored.error == "boom"


@pytest.mark.asyncio
async def test_execute_marks_task_failed_when_runner_raises():
    repo = _FakeRepository()
    task = _make_task()
    await repo.save(task)
    runner = _RecordingRunner(raises=RuntimeError("agente explodiu"))
    use_case = RunScheduledTask(repository=repo, agent_runner=runner)

    await use_case.execute(task_id="t-1")

    stored = await repo.get("t-1")
    assert stored.status == TaskStatus.FAILED
    assert "agente explodiu" in stored.error


# ---------------------------------------------------------------------------
# REQ-006 / REQ-008 — tool_scope e user_key propagados
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_propagates_tool_scope_and_owner_as_user_key():
    repo = _FakeRepository()
    task = _make_task(tool_scope=ToolScope.FULL, owner_user_key="telegram:12345")
    await repo.save(task)
    runner = _RecordingRunner(result=AgentRunResult(thread_id="th-1", status="ok"))
    use_case = RunScheduledTask(repository=repo, agent_runner=runner)

    await use_case.execute(task_id="t-1")

    assert len(runner.calls) == 1
    call = runner.calls[0]
    assert call["tool_scope"] == ToolScope.FULL
    assert call["user_key"] == "telegram:12345"
    assert call["thread_id"] == "th-1"
    assert call["prompt"] == "faz o resumo diário"


# ---------------------------------------------------------------------------
# REQ-007 — timeout
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_fails_task_when_agent_exceeds_timeout():
    repo = _FakeRepository()
    task = _make_task(timeout_seconds=1)
    await repo.save(task)
    runner = _HangingRunner()
    use_case = RunScheduledTask(repository=repo, agent_runner=runner)

    await use_case.execute(task_id="t-1")

    stored = await repo.get("t-1")
    assert stored.status == TaskStatus.FAILED
    assert stored.error is not None
    assert "timeout" in stored.error.lower()


# ---------------------------------------------------------------------------
# Tarefa inexistente — no-op tolerante
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_is_noop_when_task_does_not_exist():
    repo = _FakeRepository()
    runner = _RecordingRunner(result=AgentRunResult(thread_id="th-1", status="ok"))
    use_case = RunScheduledTask(repository=repo, agent_runner=runner)

    await use_case.execute(task_id="does-not-exist")

    assert runner.calls == []


# ---------------------------------------------------------------------------
# Injeção de dependência / pureza
# ---------------------------------------------------------------------------


def test_constructor_stores_dependencies_by_injection():
    repo = _FakeRepository()
    runner = _RecordingRunner(result=AgentRunResult(thread_id="th-1", status="ok"))
    use_case = RunScheduledTask(repository=repo, agent_runner=runner)
    assert use_case._repository is repo
    assert use_case._agent_runner is runner


def test_module_does_not_import_framework():
    src = (
        Path(__file__).parent.parent
        / "src"
        / "application"
        / "use_cases"
        / "run_scheduled_task.py"
    ).read_text()
    no_strings = re.sub(r'""".*?"""', "", src, flags=re.DOTALL)
    no_strings = re.sub(r"'''.*?'''", "", no_strings, flags=re.DOTALL)
    for forbidden in ("psycopg", "apscheduler", "langgraph", "fastapi"):
        assert not re.search(
            rf"^\s*(import|from)\s+{forbidden}\b", no_strings, flags=re.MULTILINE
        ), f"run_scheduled_task.py não pode importar {forbidden!r}"
