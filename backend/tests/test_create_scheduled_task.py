"""Testes do use case `CreateScheduledTask` (task `agendamento-jeff-cli-task-application-2`).

Puro: usa fakes das portas. Verifica:
- REQ-003: `execute()` persiste a tarefa via `repo.save()` E registra o trigger via `scheduler.schedule()`.
- Injeção de dependência via `__init__` (nada de import concreto).
- Entidade retornada é a mesma persistida.
- `tool_scope` default é `RESTRICTED` (decisão da entidade, não do use case).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.application.ports.scheduled_task_repository import ScheduledTaskRepositoryPort
from src.application.ports.task_scheduler import TaskSchedulerPort
from src.application.use_cases.create_scheduled_task import CreateScheduledTask
from src.domain.scheduling import (
    Schedule,
    ScheduledTask,
    TaskStatus,
    ToolScope,
)

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


class _FakeDeliveryResolver:
    """Fake do `ResolveDeliveryTarget.resolve` (create-1 unit tests)."""

    def __init__(
        self,
        *,
        result: str | None = None,
        error: Exception | None = None,
    ) -> None:
        self.result = result
        self.error = error
        self.calls: list[tuple[str, str | None]] = []

    async def resolve(
        self, *, user_id: str, delivery_channel: str | None
    ) -> str | None:
        self.calls.append((user_id, delivery_channel))
        if self.error is not None:
            raise self.error
        return self.result


def _use_case(
    repo: _FakeRepository | None = None,
    sched: _FakeScheduler | None = None,
    resolver: _FakeDeliveryResolver | None = None,
) -> tuple[CreateScheduledTask, _FakeRepository, _FakeScheduler, _FakeDeliveryResolver]:
    repository = repo or _FakeRepository()
    scheduler = sched or _FakeScheduler()
    delivery = resolver or _FakeDeliveryResolver()
    return (
        CreateScheduledTask(
            repository=repository,
            scheduler=scheduler,
            delivery_resolver=delivery,
        ),
        repository,
        scheduler,
        delivery,
    )


# ---------------------------------------------------------------------------
# REQ-003 — execute() persiste E agenda
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_persists_and_schedules_task():
    use_case, repo, sched, _ = _use_case()

    returned = await use_case.execute(
        task_id="t-1",
        prompt="me lembra amanhã",
        thread_id="th-1",
        schedule=Schedule(kind="once", expr="2026-12-31T23:59:00"),
    )

    # Retorna a entidade persistida
    assert isinstance(returned, ScheduledTask)
    assert returned.id == "t-1"
    assert returned.status == TaskStatus.SCHEDULED

    # Persistiu
    stored = await repo.get("t-1")
    assert stored is not None
    assert stored.id == "t-1"
    assert stored.prompt == "me lembra amanhã"

    # Agendou
    assert sched.scheduled == ["t-1"]
    assert sched.unscheduled == []


@pytest.mark.asyncio
async def test_execute_uses_provided_tool_scope():
    """REQ-006: caller pode pedir FULL explicitamente."""
    use_case, repo, _, _ = _use_case()

    returned = await use_case.execute(
        task_id="t-2",
        prompt="x",
        thread_id="th-1",
        schedule=Schedule(kind="cron", expr="0 9 * * *"),
        tool_scope=ToolScope.FULL,
    )

    assert returned.tool_scope == ToolScope.FULL
    assert (await repo.get("t-2")).tool_scope == ToolScope.FULL


@pytest.mark.asyncio
async def test_execute_default_tool_scope_is_restricted():
    """Default seguro da entidade (não do use case) é RESTRICTED."""
    use_case, _, _, _ = _use_case()

    returned = await use_case.execute(
        task_id="t-3",
        prompt="x",
        thread_id="th-1",
        schedule=Schedule(kind="once", expr="2026-01-01T00:00:00"),
    )

    assert returned.tool_scope == ToolScope.RESTRICTED


@pytest.mark.asyncio
async def test_execute_persists_optional_fields():
    """`skills` e `timeout_seconds` são repassados quando fornecidos."""
    use_case, _, _, _ = _use_case()

    returned = await use_case.execute(
        task_id="t-4",
        prompt="x",
        thread_id="th-1",
        schedule=Schedule(kind="once", expr="2026-01-01T00:00:00"),
        skills=("brand-guidelines", "canvas-design"),
        timeout_seconds=120,
    )

    assert returned.skills == ("brand-guidelines", "canvas-design")
    assert returned.timeout_seconds == 120


@pytest.mark.asyncio
async def test_execute_default_timeout_is_entity_default_when_none():
    """Quando `timeout_seconds=None`, o default da entidade (300s) é usado."""
    use_case, _, _, _ = _use_case()

    returned = await use_case.execute(
        task_id="t-5",
        prompt="x",
        thread_id="th-1",
        schedule=Schedule(kind="once", expr="2026-01-01T00:00:00"),
    )

    assert returned.timeout_seconds == 300


# ---------------------------------------------------------------------------
# scheduled-channel-routines create-1
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_persists_resolved_delivery_user_key_and_schedules():
    """unit-1: delivery_channel=whatsapp + resolver → delivery_user_key persistido."""
    resolver = _FakeDeliveryResolver(result="whatsapp:1")
    use_case, repo, sched, _ = _use_case(resolver=resolver)

    returned = await use_case.execute(
        task_id="t-wa",
        prompt="mande no zap",
        thread_id="th-1",
        schedule=Schedule(kind="once", expr="2026-12-31T23:59:00"),
        owner_user_key="web:owner-uuid",
        owner_user_id="owner-uuid",
        delivery_channel="whatsapp",
    )

    assert returned.delivery_user_key == "whatsapp:1"
    assert returned.owner_user_key == "web:owner-uuid"
    stored = await repo.get("t-wa")
    assert stored is not None
    assert stored.delivery_user_key == "whatsapp:1"
    assert sched.scheduled == ["t-wa"]
    assert resolver.calls == [("owner-uuid", "whatsapp")]
    # owner nunca vem do delivery_channel
    assert returned.owner_user_key == "web:owner-uuid"


@pytest.mark.asyncio
async def test_execute_omitted_delivery_channel_leaves_delivery_user_key_none():
    """REQ-001: omitido → delivery_user_key None (fallback owner no domínio)."""
    use_case, _, _, resolver = _use_case()

    returned = await use_case.execute(
        task_id="t-omit",
        prompt="x",
        thread_id="th-1",
        schedule=Schedule(kind="once", expr="2026-01-01T00:00:00"),
        owner_user_key="web:owner-uuid",
        owner_user_id="owner-uuid",
    )

    assert returned.delivery_user_key is None
    assert returned.effective_delivery_user_key == "web:owner-uuid"
    assert resolver.calls == []


@pytest.mark.asyncio
async def test_execute_without_link_does_not_persist_or_schedule():
    """unit-2: resolver falha → nada salvo e scheduler não chamado."""
    from src.domain.shared.errors import DomainError

    resolver = _FakeDeliveryResolver(
        error=DomainError("canal whatsapp sem vínculo ativo")
    )
    use_case, repo, sched, _ = _use_case(resolver=resolver)

    with pytest.raises(DomainError, match="whatsapp"):
        await use_case.execute(
            task_id="t-fail",
            prompt="x",
            thread_id="th-1",
            schedule=Schedule(kind="once", expr="2026-01-01T00:00:00"),
            owner_user_key="web:owner-uuid",
            owner_user_id="owner-uuid",
            delivery_channel="whatsapp",
        )

    assert await repo.get("t-fail") is None
    assert sched.scheduled == []


# ---------------------------------------------------------------------------
# Injeção de dependência
# ---------------------------------------------------------------------------


def test_constructor_stores_dependencies_by_injection():
    use_case, repo, sched, resolver = _use_case()
    assert use_case._repository is repo
    assert use_case._scheduler is sched
    assert use_case._delivery_resolver is resolver


def test_constructor_does_not_import_framework():
    """Garantia estática: o módulo não pode importar infra concreta."""
    src = (
        Path(__file__).parent.parent
        / "src"
        / "application"
        / "use_cases"
        / "create_scheduled_task.py"
    ).read_text()
    no_strings = re.sub(r'""".*?""""', "", src, flags=re.DOTALL)
    no_strings = re.sub(r"'''.*?'''", "", no_strings, flags=re.DOTALL)
    for forbidden in ("psycopg", "apscheduler", "langgraph", "fastapi"):
        assert not re.search(
            rf"^\s*(import|from)\s+{forbidden}\b", no_strings, flags=re.MULTILINE
        ), f"create_scheduled_task.py não pode importar {forbidden!r}"


# ---------------------------------------------------------------------------
# Erros de domínio propagam (validação fica na entidade)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_rejects_empty_prompt_without_persisting():
    """`DomainError` da entidade deve propagar; nada é persistido nem agendado."""
    use_case, repo, sched, _ = _use_case()

    with pytest.raises(Exception):  # DomainError, duck-typed
        await use_case.execute(
            task_id="t-bad",
            prompt="   ",
            thread_id="th-1",
            schedule=Schedule(kind="once", expr="2026-01-01T00:00:00"),
        )

    # Nada vazou pra persistência nem pro scheduler
    assert await repo.get("t-bad") is None
    assert sched.scheduled == []
