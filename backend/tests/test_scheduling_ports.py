"""Testes das 3 portas de `application/ports/` do scheduling.

Puro: não toca em framework. Verifica que:
- `ScheduledTaskRepositoryPort` (REQ-001) define save/get/list_all/delete como ABC.
- `ScheduledTaskRepositoryPort.get()` retorna `ScheduledTask | None` (nunca exceção).
- `TaskSchedulerPort` (REQ-005) define schedule/unschedule, sem `apscheduler` no nome.
- `AgentRunnerPort.run(thread_id, prompt, skills, tool_scope)` retorna `AgentRunResult`.
- Nenhuma porta importa framework proibido (psycopg/apscheduler/langgraph).
"""
from __future__ import annotations

import inspect
import re
from abc import ABC
from pathlib import Path
from typing import get_type_hints

import pytest

from src.application.ports.agent_runner import AgentRunnerPort, AgentRunResult
from src.application.ports.scheduled_task_repository import ScheduledTaskRepositoryPort
from src.application.ports.task_scheduler import TaskSchedulerPort
from src.domain.scheduling import (
    Schedule,
    ScheduledTask,
    TaskStatus,
    ToolScope,
)

# ---------------------------------------------------------------------------
# REQ-001 — ScheduledTaskRepositoryPort
# ---------------------------------------------------------------------------


def test_repository_port_is_abstract_base_class():
    assert issubclass(ScheduledTaskRepositoryPort, ABC)
    # Não pode ser instanciado diretamente
    with pytest.raises(TypeError):
        ScheduledTaskRepositoryPort()  # type: ignore[abstract]


@pytest.mark.parametrize(
    "method_name", ["save", "get", "list_all", "delete"]
)
def test_repository_port_defines_required_methods(method_name: str):
    assert hasattr(ScheduledTaskRepositoryPort, method_name)
    method = getattr(ScheduledTaskRepositoryPort, method_name)
    assert getattr(method, "__isabstractmethod__", False), (
        f"{method_name} deve ser @abstractmethod"
    )


def test_repository_port_get_returns_optional_via_type_hints():
    """`get()` documentado e tipado como `ScheduledTask | None`."""
    hints = get_type_hints(ScheduledTaskRepositoryPort.get)
    assert "return" in hints
    # `Optional[ScheduledTask]` (Union[X, None]) deve aparecer nas anotações
    ann = str(hints["return"])
    assert "ScheduledTask" in ann
    assert "None" in ann


def test_repository_port_get_signature_accepts_task_id():
    sig = inspect.signature(ScheduledTaskRepositoryPort.get)
    params = list(sig.parameters.values())
    assert len(params) == 2  # self + task_id
    assert params[1].name == "task_id"


def test_repository_port_methods_are_coroutines():
    """Todas as operações do repositório são async (consistente com image_gen)."""
    for name in ("save", "get", "list_all", "delete"):
        method = getattr(ScheduledTaskRepositoryPort, name)
        assert inspect.iscoroutinefunction(method), f"{name} deve ser async"


# ---------------------------------------------------------------------------
# REQ-005 — TaskSchedulerPort (sem APScheduler no nome)
# ---------------------------------------------------------------------------


def test_task_scheduler_port_is_abstract_base_class():
    assert issubclass(TaskSchedulerPort, ABC)
    with pytest.raises(TypeError):
        TaskSchedulerPort()  # type: ignore[abstract]


def test_task_scheduler_port_defines_schedule_and_unschedule():
    assert hasattr(TaskSchedulerPort, "schedule")
    assert hasattr(TaskSchedulerPort, "unschedule")
    for name in ("schedule", "unschedule"):
        method = getattr(TaskSchedulerPort, name)
        assert getattr(method, "__isabstractmethod__", False)


def test_task_scheduler_port_signature_uses_task_and_task_id():
    """schedule(task) / unschedule(task_id) — sem import de APScheduler."""
    schedule_sig = inspect.signature(TaskSchedulerPort.schedule)
    assert "task" in schedule_sig.parameters

    unschedule_sig = inspect.signature(TaskSchedulerPort.unschedule)
    assert "task_id" in unschedule_sig.parameters


def test_task_scheduler_port_does_not_reference_apscheduler_in_name():
    src = (Path(__file__).parent.parent / "src" / "application" / "ports" / "task_scheduler.py").read_text()
    # Remove docstrings e comentários antes de checar (evita menção explicativa)
    no_strings = re.sub(r'""".*?"""', "", src, flags=re.DOTALL)
    no_strings = re.sub(r"'''.*?'''", "", no_strings, flags=re.DOTALL)
    assert "apscheduler" not in no_strings.lower(), (
        "TaskSchedulerPort não pode mencionar APScheduler — abstração deve ficar"
        " livre de mecanismo de tick"
    )


# ---------------------------------------------------------------------------
# AgentRunnerPort + AgentRunResult
# ---------------------------------------------------------------------------


def test_agent_run_result_is_frozen_dataclass():
    """`AgentRunResult` é dataclass congelado, no molde de `GeneratedImage`."""
    import dataclasses

    assert dataclasses.is_dataclass(AgentRunResult)
    r = AgentRunResult(thread_id="th-1", status="ok", error=None)
    with pytest.raises(dataclasses.FrozenInstanceError):
        r.thread_id = "th-2"  # type: ignore[misc]


def test_agent_run_result_default_error_is_none():
    r = AgentRunResult(thread_id="th-1", status="ok")
    assert r.error is None


def test_agent_runner_port_is_abstract_base_class():
    assert issubclass(AgentRunnerPort, ABC)
    with pytest.raises(TypeError):
        AgentRunnerPort()  # type: ignore[abstract]


def test_agent_runner_port_run_signature():
    """`run(thread_id, prompt, skills, tool_scope)` retorna AgentRunResult."""
    sig = inspect.signature(AgentRunnerPort.run)
    params = list(sig.parameters.keys())
    # self, thread_id, prompt, skills, tool_scope (5 params)
    for required in ("thread_id", "prompt", "skills", "tool_scope"):
        assert required in params, f"run() deve aceitar {required!r}"

    hints = get_type_hints(AgentRunnerPort.run)
    assert "AgentRunResult" in str(hints["return"])


def test_agent_runner_port_run_is_coroutine():
    assert inspect.iscoroutinefunction(AgentRunnerPort.run)


# ---------------------------------------------------------------------------
# Pureza: zero import proibido nas 3 portas
# ---------------------------------------------------------------------------


_PORTS_DIR = Path(__file__).parent.parent / "src" / "application" / "ports"
_FORBIDDEN = ("psycopg", "apscheduler", "langgraph")


@pytest.mark.parametrize(
    "module",
    [
        "scheduled_task_repository.py",
        "task_scheduler.py",
        "agent_runner.py",
    ],
)
def test_port_module_has_no_framework_imports(module: str):
    src = (_PORTS_DIR / module).read_text()
    no_strings = re.sub(r'""".*?""""', "", src, flags=re.DOTALL)
    no_strings = re.sub(r"'''.*?'''", "", no_strings, flags=re.DOTALL)
    for forbidden in _FORBIDDEN:
        assert not re.search(
            rf"^\s*(import|from)\s+{forbidden}\b", no_strings, flags=re.MULTILINE
        ), f"{module} não pode importar {forbidden!r}"


# ---------------------------------------------------------------------------
# Integração leve: fakes implementam as portas e respeitam contratos
# ---------------------------------------------------------------------------


class _FakeRepository(ScheduledTaskRepositoryPort):
    """Implementação fake em memória para validar o contrato da porta."""

    def __init__(self) -> None:
        self._store: dict[str, ScheduledTask] = {}

    async def save(self, task: ScheduledTask) -> None:
        self._store[task.id] = task

    async def get(self, task_id: str) -> ScheduledTask | None:
        return self._store.get(task_id)

    async def list_all(self) -> list[ScheduledTask]:
        return list(self._store.values())

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
        return AgentRunResult(thread_id=thread_id, status="ok")


@pytest.mark.asyncio
async def test_fake_repository_round_trip():
    repo = _FakeRepository()
    task = ScheduledTask(
        id="t-1",
        prompt="p",
        thread_id="th-1",
        schedule=Schedule(kind="once", expr="2026-01-01T00:00:00"),
    )
    assert await repo.get("t-1") is None  # REQ: nunca exceção
    await repo.save(task)
    got = await repo.get("t-1")
    assert got is not None
    assert got.id == "t-1"
    assert got.status == TaskStatus.SCHEDULED
    await repo.delete("t-1")
    assert await repo.get("t-1") is None


@pytest.mark.asyncio
async def test_fake_scheduler_records_calls():
    sched = _FakeScheduler()
    task = ScheduledTask(
        id="t-2",
        prompt="p",
        thread_id="th-1",
        schedule=Schedule(kind="cron", expr="0 9 * * *"),
    )
    await sched.schedule(task)
    await sched.unschedule("t-2")
    assert sched.scheduled == ["t-2"]
    assert sched.unscheduled == ["t-2"]


@pytest.mark.asyncio
async def test_fake_runner_returns_agent_run_result():
    runner = _FakeRunner()
    result = await runner.run(
        thread_id="th-1", prompt="oi", skills=(), tool_scope=ToolScope.RESTRICTED
    )
    assert isinstance(result, AgentRunResult)
    assert result.thread_id == "th-1"
    assert result.status == "ok"
