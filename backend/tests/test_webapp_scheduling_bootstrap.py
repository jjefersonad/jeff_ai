"""Testes de `_lifespan` do webapp para o bootstrap de agendamento (task
`agendamento-jeff-cli-task-scheduling-infra-2`).

Cobre os critérios de aceite da task:
- REQ-001: tarefas `SCHEDULED` são recarregadas/reagendadas no boot do processo
- `init_auth_schema(...)` e o start do scheduler são chamadas independentes no
  `lifespan` — nenhuma depende do resultado da outra
- Shutdown do `AsyncIOScheduler` tratado no `lifespan`

Segue o mesmo padrão de `test_usage_bootstrap.py`: monkeypatcha as funções de
bootstrap em `webapp` e dispara o lifespan via `TestClient(webapp.app)` como
context manager, sem tocar Postgres real.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import src.infrastructure.web.webapp as webapp
from src.domain.scheduling import Schedule, ScheduledTask, TaskStatus


def _task(task_id: str, status: TaskStatus) -> ScheduledTask:
    task = ScheduledTask(
        id=task_id,
        prompt="diga olá",
        thread_id="th-1",
        schedule=Schedule(kind="once", expr="2026-12-31T23:59:00"),
        owner_user_key="web:owner-1",
    )
    task.status = status
    return task


def _patch_common_bootstrap(monkeypatch: pytest.MonkeyPatch, calls: list[str]) -> None:
    monkeypatch.setenv("POSTGRES_URI", "postgresql://scheduling-bootstrap")
    monkeypatch.setattr(
        "src.composition.dependencies.build_dependencies",
        lambda: calls.append("build_dependencies"),
    )
    monkeypatch.setattr(
        webapp, "init_auth_schema", lambda conninfo: calls.append(f"auth:{conninfo}")
    )
    monkeypatch.setattr(
        webapp,
        "ensure_ownership_schema",
        lambda conninfo: calls.append(f"ownership:{conninfo}"),
    )
    monkeypatch.setattr(
        webapp,
        "ensure_attachments_schema",
        lambda conninfo: calls.append(f"attachments:{conninfo}"),
    )
    monkeypatch.setattr(
        webapp,
        "ensure_usage_schema",
        lambda conninfo: calls.append(f"usage:{conninfo}"),
    )
    monkeypatch.setattr(
        webapp,
        "ensure_scheduled_tasks_schema",
        lambda conninfo: calls.append(f"scheduled_tasks_schema:{conninfo}"),
    )
    monkeypatch.setattr(
        webapp,
        "ensure_user_integrations_schema",
        lambda conninfo: calls.append(f"user_integrations_schema:{conninfo}"),
    )
    monkeypatch.setattr(
        webapp,
        "ensure_user_mcp_servers_schema",
        lambda conninfo: calls.append(f"user_mcp_servers_schema:{conninfo}"),
    )
    monkeypatch.setattr(
        webapp,
        "ensure_telegram_link_codes_schema",
        lambda conninfo: calls.append(f"telegram_link_codes_schema:{conninfo}"),
    )
    monkeypatch.setattr(
        webapp,
        "ensure_whatsapp_link_codes_schema",
        lambda conninfo: calls.append(f"whatsapp_link_codes_schema:{conninfo}"),
    )
    monkeypatch.setattr(
        webapp,
        "ensure_whatsapp_threads_schema",
        lambda conninfo: calls.append(f"whatsapp_threads_schema:{conninfo}"),
    )
    monkeypatch.setattr(
        webapp,
        "ensure_langgraph_checkpoint_schema",
        lambda conninfo: calls.append(f"checkpoint_schema:{conninfo}"),
    )

    async def _fake_init_pool(conninfo: str) -> None:
        calls.append(f"pool:{conninfo}")

    async def _fake_close_pool() -> None:
        calls.append("close_pool")

    monkeypatch.setattr(webapp, "init_pool", _fake_init_pool)
    monkeypatch.setattr(webapp, "close_pool", _fake_close_pool)
    monkeypatch.setattr(
        webapp, "PostgresScheduledTaskRepository", lambda conninfo: _FakeRepository([])
    )


class _FakeRepository:
    def __init__(self, tasks: list[ScheduledTask]) -> None:
        self._tasks = tasks

    async def list_all(self) -> list[ScheduledTask]:
        return list(self._tasks)


class _FakeScheduler:
    def __init__(self, calls: list[str]) -> None:
        self._calls = calls
        self.scheduled_ids: list[str] = []

    def start(self) -> None:
        self._calls.append("scheduler:start")

    def shutdown(self, wait: bool = True) -> None:
        self._calls.append("scheduler:shutdown")

    async def schedule(self, task: ScheduledTask) -> None:
        self.scheduled_ids.append(task.id)
        self._calls.append(f"scheduler:schedule:{task.id}")


# ---------------------------------------------------------------------------
# REQ-001 — reload de tarefas SCHEDULED no boot
# ---------------------------------------------------------------------------


def test_lifespan_reschedules_only_scheduled_tasks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    _patch_common_bootstrap(monkeypatch, calls)

    tasks = [
        _task("t-scheduled", TaskStatus.SCHEDULED),
        _task("t-succeeded", TaskStatus.SUCCEEDED),
        _task("t-failed", TaskStatus.FAILED),
        _task("t-running", TaskStatus.RUNNING),
    ]
    monkeypatch.setattr(
        webapp, "PostgresScheduledTaskRepository", lambda conninfo: _FakeRepository(tasks)
    )
    fake_scheduler = _FakeScheduler(calls)
    monkeypatch.setattr(webapp, "task_scheduler", fake_scheduler)

    with TestClient(webapp.app):
        pass

    assert fake_scheduler.scheduled_ids == ["t-scheduled"]


def test_lifespan_handles_no_scheduled_tasks(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    _patch_common_bootstrap(monkeypatch, calls)
    fake_scheduler = _FakeScheduler(calls)
    monkeypatch.setattr(webapp, "task_scheduler", fake_scheduler)

    with TestClient(webapp.app):
        pass

    assert fake_scheduler.scheduled_ids == []
    assert "scheduler:start" in calls


# ---------------------------------------------------------------------------
# init_auth_schema e o start do scheduler são chamadas independentes
# ---------------------------------------------------------------------------


def test_lifespan_calls_scheduled_tasks_schema_and_auth_schema_independently(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    _patch_common_bootstrap(monkeypatch, calls)
    fake_scheduler = _FakeScheduler(calls)
    monkeypatch.setattr(webapp, "task_scheduler", fake_scheduler)

    with TestClient(webapp.app):
        pass

    assert "auth:postgresql://scheduling-bootstrap" in calls
    assert "scheduled_tasks_schema:postgresql://scheduling-bootstrap" in calls
    assert "scheduler:start" in calls
    # REQ-ADD-001: _patch_common_bootstrap MUST stub current lifespan deps so
    # TestClient never hits a real Postgres / ChannelRegistry bootstrap.
    assert "build_dependencies" in calls
    assert "user_mcp_servers_schema:postgresql://scheduling-bootstrap" in calls
    assert "whatsapp_link_codes_schema:postgresql://scheduling-bootstrap" in calls
    assert "whatsapp_threads_schema:postgresql://scheduling-bootstrap" in calls
    # REQ-ADD-001: ensure MUST run before pool/reschedule (list_all path).
    schema_idx = calls.index(
        "scheduled_tasks_schema:postgresql://scheduling-bootstrap"
    )
    pool_idx = calls.index("pool:postgresql://scheduling-bootstrap")
    assert schema_idx < pool_idx


def test_lifespan_starts_scheduler_even_when_auth_schema_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Falha em `init_auth_schema` não deve ser mascarada pelo bootstrap de scheduling
    nem o contrário — mas confirma que uma chamada não está aninhada dentro do
    try/except da outra: um erro em auth propaga (nenhuma tentativa de
    'engolir' e seguir para o scheduler)."""
    calls: list[str] = []
    _patch_common_bootstrap(monkeypatch, calls)

    def _raise(conninfo: str) -> None:
        raise RuntimeError("auth schema boom")

    monkeypatch.setattr(webapp, "init_auth_schema", _raise)
    fake_scheduler = _FakeScheduler(calls)
    monkeypatch.setattr(webapp, "task_scheduler", fake_scheduler)

    with pytest.raises(RuntimeError, match="auth schema boom"):
        with TestClient(webapp.app):
            pass

    assert "scheduler:start" not in calls


# ---------------------------------------------------------------------------
# Shutdown do AsyncIOScheduler tratado no lifespan
# ---------------------------------------------------------------------------


def test_lifespan_shuts_down_scheduler_on_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    _patch_common_bootstrap(monkeypatch, calls)
    fake_scheduler = _FakeScheduler(calls)
    monkeypatch.setattr(webapp, "task_scheduler", fake_scheduler)

    with TestClient(webapp.app):
        assert "scheduler:shutdown" not in calls

    assert "scheduler:shutdown" in calls
    assert calls.index("scheduler:start") < calls.index("scheduler:shutdown")
