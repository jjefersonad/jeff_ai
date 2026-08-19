"""Persistência e validação de `ScheduledTask.profile_id` (sched-1 / REQ-015).

Create com perfil ativo do dono grava o UUID. Cross-user, arquivado ou
inexistente → DomainError e nenhum trigger. Sem persistir perfil inválido.
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.application.ports.scheduled_task_repository import ScheduledTaskRepositoryPort
from src.application.ports.task_scheduler import TaskSchedulerPort
from src.application.use_cases.create_scheduled_task import CreateScheduledTask
from src.application.use_cases.get_agent_profile import GetAgentProfile
from src.application.use_cases.update_scheduled_task import UpdateScheduledTask
from src.domain.agents import AgentProfile
from src.domain.scheduling import Schedule, ScheduledTask
from src.domain.shared.errors import DomainError
from tests.agent_profile_repository_fakes import InMemoryAgentProfileRepository


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
    async def resolve(
        self, *, user_id: str, delivery_channel: str | None
    ) -> str | None:
        return None


def _profile(
    *,
    profile_id: str = "p-coder",
    user_id: str = "user-a",
    slug: str | None = None,
    archived_at: datetime | None = None,
) -> AgentProfile:
    now = datetime.now(UTC)
    return AgentProfile(
        id=profile_id,
        user_id=user_id,
        name="Coder",
        slug=slug or f"coder-{profile_id}",
        system_prompt="x",
        archived_at=archived_at,
        created_at=now,
        updated_at=now,
    )


def _use_case(
    profiles: InMemoryAgentProfileRepository,
) -> tuple[CreateScheduledTask, _FakeRepository, _FakeScheduler]:
    repo = _FakeRepository()
    sched = _FakeScheduler()
    use_case = CreateScheduledTask(
        repository=repo,
        scheduler=sched,
        delivery_resolver=_FakeDeliveryResolver(),
        get_agent_profile=GetAgentProfile(repository=profiles),
    )
    return use_case, repo, sched


@pytest.mark.asyncio
async def test_create_stores_owned_active_profile_id() -> None:
    """WHEN owner creates with their active profile_id THEN the row stores it."""
    profiles = InMemoryAgentProfileRepository()
    seeded = await profiles.create(_profile())
    use_case, repo, sched = _use_case(profiles)

    task = await use_case.execute(
        task_id="t-1",
        prompt="roda o coder",
        thread_id="th-1",
        schedule=Schedule(kind="once", expr="2026-12-31T23:59:00"),
        owner_user_key="web:user-a",
        owner_user_id="user-a",
        profile_id=seeded.id,
    )

    assert task.profile_id == seeded.id
    saved = await repo.get("t-1")
    assert saved is not None
    assert saved.profile_id == seeded.id
    assert sched.scheduled == ["t-1"]


@pytest.mark.asyncio
async def test_create_rejects_cross_user_profile_without_trigger() -> None:
    """WHEN profile_id belongs to another user THEN 422-equivalent, no trigger."""
    profiles = InMemoryAgentProfileRepository()
    other = await profiles.create(_profile(profile_id="p-b", user_id="user-b"))
    use_case, repo, sched = _use_case(profiles)

    with pytest.raises(DomainError, match="profile_id"):
        await use_case.execute(
            task_id="t-x",
            prompt="hijack",
            thread_id="th-1",
            schedule=Schedule(kind="once", expr="2026-12-31T23:59:00"),
            owner_user_key="web:user-a",
            owner_user_id="user-a",
            profile_id=other.id,
        )

    assert await repo.get("t-x") is None
    assert sched.scheduled == []


@pytest.mark.asyncio
async def test_create_rejects_archived_profile_without_trigger() -> None:
    """WHEN profile_id is archived THEN DomainError and no scheduler trigger."""
    profiles = InMemoryAgentProfileRepository()
    archived = await profiles.create(
        _profile(archived_at=datetime.now(UTC))
    )
    use_case, repo, sched = _use_case(profiles)

    with pytest.raises(DomainError, match="profile_id"):
        await use_case.execute(
            task_id="t-arch",
            prompt="arquivo",
            thread_id="th-1",
            schedule=Schedule(kind="once", expr="2026-12-31T23:59:00"),
            owner_user_key="web:user-a",
            owner_user_id="user-a",
            profile_id=archived.id,
        )

    assert await repo.get("t-arch") is None
    assert sched.scheduled == []


@pytest.mark.asyncio
async def test_create_rejects_missing_profile_without_trigger() -> None:
    """WHEN profile_id does not exist THEN DomainError and no scheduler trigger."""
    profiles = InMemoryAgentProfileRepository()
    use_case, repo, sched = _use_case(profiles)

    with pytest.raises(DomainError, match="profile_id"):
        await use_case.execute(
            task_id="t-miss",
            prompt="sumiu",
            thread_id="th-1",
            schedule=Schedule(kind="once", expr="2026-12-31T23:59:00"),
            owner_user_key="web:user-a",
            owner_user_id="user-a",
            profile_id="does-not-exist",
        )

    assert await repo.get("t-miss") is None
    assert sched.scheduled == []


@pytest.mark.asyncio
async def test_create_omitted_profile_inherits_session_id() -> None:
    """WHEN profile_id is omitted and session has one THEN the task stores that id."""
    profiles = InMemoryAgentProfileRepository()
    seeded = await profiles.create(_profile())
    use_case, repo, sched = _use_case(profiles)

    task = await use_case.execute(
        task_id="t-inherit",
        prompt="herda",
        thread_id="th-1",
        schedule=Schedule(kind="once", expr="2026-12-31T23:59:00"),
        owner_user_key="web:user-a",
        owner_user_id="user-a",
        session_profile_id=seeded.id,
    )

    assert task.profile_id == seeded.id
    saved = await repo.get("t-inherit")
    assert saved is not None
    assert saved.profile_id == seeded.id
    assert sched.scheduled == ["t-inherit"]


@pytest.mark.asyncio
async def test_create_omitted_profile_without_session_is_null() -> None:
    """WHEN create omits profile_id and the session has none THEN profile_id is null."""
    profiles = InMemoryAgentProfileRepository()
    await profiles.create(_profile())
    use_case, repo, _sched = _use_case(profiles)

    task = await use_case.execute(
        task_id="t-null",
        prompt="sem overlay",
        thread_id="th-1",
        schedule=Schedule(kind="once", expr="2026-12-31T23:59:00"),
        owner_user_key="web:user-a",
        owner_user_id="user-a",
    )

    assert task.profile_id is None
    saved = await repo.get("t-null")
    assert saved is not None
    assert saved.profile_id is None


@pytest.mark.asyncio
async def test_tool_omitted_profile_inherits_configurable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WHEN create_scheduled_task omits profile_id and configurable has one THEN stores it."""
    import src.tools.scheduling_tools as st

    profiles = InMemoryAgentProfileRepository()
    seeded = await profiles.create(_profile())
    repo = _FakeRepository()
    sched = _FakeScheduler()
    monkeypatch.setattr(
        st, "get_config", lambda: {
            "configurable": {
                "user_key": "web:user-a",
                "thread_id": "th-9",
                "profile_id": seeded.id,
            }
        },
    )

    async def _fake_resolve() -> str:
        return "user-a"

    monkeypatch.setattr(st, "resolve_user_id", _fake_resolve)
    monkeypatch.setattr(
        st,
        "build_create_scheduled_task",
        lambda: CreateScheduledTask(
            repository=repo,
            scheduler=sched,
            delivery_resolver=_FakeDeliveryResolver(),
            get_agent_profile=GetAgentProfile(repository=profiles),
        ),
    )

    result = await st.create_scheduled_task.ainvoke(
        {
            "prompt": "lembra amanhã",
            "schedule_kind": "once",
            "schedule_expr": "2026-12-31T23:59:00",
        }
    )

    assert "error" not in result
    saved = await repo.get(result["id"])
    assert saved is not None
    assert saved.profile_id == seeded.id
    assert result["profile_id"] == seeded.id


@pytest.mark.asyncio
async def test_tool_omitted_profile_without_session_is_null(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WHEN the tool omits profile_id and the session has none THEN profile_id is null."""
    import src.tools.scheduling_tools as st

    profiles = InMemoryAgentProfileRepository()
    repo = _FakeRepository()
    sched = _FakeScheduler()
    monkeypatch.setattr(
        st,
        "get_config",
        lambda: {"configurable": {"user_key": "web:user-a", "thread_id": "th-9"}},
    )

    async def _fake_resolve() -> str:
        return "user-a"

    monkeypatch.setattr(st, "resolve_user_id", _fake_resolve)
    monkeypatch.setattr(
        st,
        "build_create_scheduled_task",
        lambda: CreateScheduledTask(
            repository=repo,
            scheduler=sched,
            delivery_resolver=_FakeDeliveryResolver(),
            get_agent_profile=GetAgentProfile(repository=profiles),
        ),
    )

    result = await st.create_scheduled_task.ainvoke(
        {
            "prompt": "lembra amanhã",
            "schedule_kind": "once",
            "schedule_expr": "2026-12-31T23:59:00",
        }
    )

    assert "error" not in result
    saved = await repo.get(result["id"])
    assert saved is not None
    assert saved.profile_id is None
    assert result.get("profile_id") is None


def test_tool_does_not_accept_owner_user_key() -> None:
    """REQ-015: a tool não aceita owner_user_key do modelo; profile_id explícito é permitido."""
    import inspect

    import src.tools.scheduling_tools as st

    sig = inspect.signature(st.create_scheduled_task.coroutine)
    assert "owner_user_key" not in sig.parameters
    assert "owner_user_id" not in sig.parameters
    assert "profile_id" in sig.parameters


# ---------------------------------------------------------------------------
# Update (REQ-009)
# ---------------------------------------------------------------------------


def _update_use_case(
    repo: _FakeRepository,
    sched: _FakeScheduler,
    profiles: InMemoryAgentProfileRepository,
) -> UpdateScheduledTask:
    return UpdateScheduledTask(
        repository=repo,
        scheduler=sched,
        delivery_resolver=_FakeDeliveryResolver(),
        get_agent_profile=GetAgentProfile(repository=profiles),
    )


def _scheduled(**overrides: object) -> ScheduledTask:
    defaults: dict[str, object] = {
        "id": "t-1",
        "prompt": "olá",
        "thread_id": "th-1",
        "schedule": Schedule(kind="once", expr="2026-01-01T00:00:00"),
        "owner_user_key": "web:user-a",
        "profile_id": "p-coder",
    }
    defaults.update(overrides)
    return ScheduledTask(**defaults)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_update_swaps_owned_active_profile_id() -> None:
    """WHEN owner PATCHes SCHEDULED with another owned active profile THEN row updates."""
    profiles = InMemoryAgentProfileRepository()
    first = await profiles.create(_profile(profile_id="p-coder"))
    second = await profiles.create(_profile(profile_id="p-marketer", slug="marketer"))
    repo = _FakeRepository()
    sched = _FakeScheduler()
    await repo.save(_scheduled(profile_id=first.id))
    use_case = _update_use_case(repo, sched, profiles)

    returned = await use_case.execute(
        task_id="t-1",
        caller_user_key="web:user-a",
        caller_user_id="user-a",
        is_admin=False,
        profile_id=second.id,
    )

    assert returned is not None
    assert returned.profile_id == second.id
    stored = await repo.get("t-1")
    assert stored is not None
    assert stored.profile_id == second.id


@pytest.mark.asyncio
async def test_update_rejects_cross_user_profile_id() -> None:
    """WHEN PATCH profile_id belongs to another user THEN DomainError, row unchanged."""
    profiles = InMemoryAgentProfileRepository()
    mine = await profiles.create(_profile())
    other = await profiles.create(_profile(profile_id="p-b", user_id="user-b"))
    repo = _FakeRepository()
    sched = _FakeScheduler()
    await repo.save(_scheduled(profile_id=mine.id))
    use_case = _update_use_case(repo, sched, profiles)

    with pytest.raises(DomainError, match="profile_id"):
        await use_case.execute(
            task_id="t-1",
            caller_user_key="web:user-a",
            caller_user_id="user-a",
            is_admin=False,
            profile_id=other.id,
        )

    stored = await repo.get("t-1")
    assert stored is not None
    assert stored.profile_id == mine.id


@pytest.mark.asyncio
async def test_update_can_clear_profile_id_to_null() -> None:
    """WHEN PATCH profile_id is null THEN the overlay is cleared."""
    profiles = InMemoryAgentProfileRepository()
    mine = await profiles.create(_profile())
    repo = _FakeRepository()
    sched = _FakeScheduler()
    await repo.save(_scheduled(profile_id=mine.id))
    use_case = _update_use_case(repo, sched, profiles)

    returned = await use_case.execute(
        task_id="t-1",
        caller_user_key="web:user-a",
        caller_user_id="user-a",
        is_admin=False,
        profile_id=None,
    )

    assert returned is not None
    assert returned.profile_id is None
    stored = await repo.get("t-1")
    assert stored is not None
    assert stored.profile_id is None
