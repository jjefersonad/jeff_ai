"""Testes de `GET`/`POST`/`PATCH`/`DELETE /api/scheduled-tasks` (agendamento-jeff-cli-frontend).

Cobre REQ-001 (listagem escopada por papel), REQ-002 (criação com dono
resolvido da sessão), REQ-003 (edição restrita a tarefas SCHEDULED) e REQ-004
(exclusão via cancelamento existente) do spec `scheduled-tasks-rest-api`.
Persistência e scheduler são fakes injetados via override de dependency —
mesmo padrão de `test_list_and_cancel_scheduled_tasks.py`/`test_usage_router.py`.
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timezone

import pytest
from fastapi.testclient import TestClient

import src.infrastructure.web.scheduling_router as scheduling_router
import src.infrastructure.web.webapp as webapp
from src.application.ports.scheduled_task_repository import ScheduledTaskRepositoryPort
from src.application.ports.task_scheduler import TaskSchedulerPort
from src.application.ports.user_integration_repository import (
    UserIntegrationRepositoryPort,
)
from src.application.use_cases.resolve_delivery_target import ResolveDeliveryTarget
from src.domain.integrations import UserIntegration
from src.domain.scheduling import Schedule, ScheduledTask, TaskStatus
from src.infrastructure.auth.dependencies import require_auth
from src.infrastructure.auth.users import User

_ADMIN = User(
    id="admin-1",
    username="alice",
    password_hash="h",
    role="admin",
    is_active=True,
    created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
)
_USER_A = User(
    id="user-a",
    username="bob",
    password_hash="h",
    role="user",
    is_active=True,
    created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
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


class _FakeScheduler(TaskSchedulerPort):
    def __init__(self) -> None:
        self.scheduled: list[str] = []
        self.unscheduled: list[str] = []

    async def schedule(self, task: ScheduledTask) -> None:
        self.scheduled.append(task.id)

    async def unschedule(self, task_id: str) -> None:
        self.unscheduled.append(task_id)


class _FakeIntegrationRepository(UserIntegrationRepositoryPort):
    def __init__(self) -> None:
        self._store: dict[str, UserIntegration] = {}

    async def save(self, integration: UserIntegration) -> None:
        self._store[integration.id] = integration

    async def get(self, integration_id: str) -> UserIntegration | None:
        return self._store.get(integration_id)

    async def list_by_user(self, user_id: str) -> list[UserIntegration]:
        return [i for i in self._store.values() if i.user_id == user_id]

    async def list_all(self) -> list[UserIntegration]:
        return list(self._store.values())

    async def delete(self, integration_id: str) -> None:
        self._store.pop(integration_id, None)


def _make_task(*, id_: str, owner: str) -> ScheduledTask:
    return ScheduledTask(
        id=id_,
        prompt="x",
        thread_id="th-1",
        schedule=Schedule(kind="once", expr="2026-12-31T23:59:00"),
        owner_user_key=owner,
    )


def _integration(
    *,
    id_: str,
    user_id: str,
    integration_type: str,
    config: dict[str, object],
) -> UserIntegration:
    return UserIntegration(
        id=id_,
        user_id=user_id,
        integration_type=integration_type,
        config=config,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


@pytest.fixture
def repo() -> _FakeRepository:
    return _FakeRepository()


@pytest.fixture
def scheduler() -> _FakeScheduler:
    return _FakeScheduler()


@pytest.fixture
def integrations() -> _FakeIntegrationRepository:
    return _FakeIntegrationRepository()


@pytest.fixture
def client(
    repo: _FakeRepository,
    scheduler: _FakeScheduler,
    integrations: _FakeIntegrationRepository,
):
    """Cliente do webapp com repo/scheduler/auth sobrescritos pelo teste."""
    resolver = ResolveDeliveryTarget(repository=integrations)
    webapp.app.dependency_overrides[scheduling_router._scheduled_task_repository] = (
        lambda: repo
    )
    webapp.app.dependency_overrides[scheduling_router._task_scheduler_dependency] = (
        lambda: scheduler
    )
    webapp.app.dependency_overrides[scheduling_router._delivery_target_resolver] = (
        lambda: resolver
    )
    try:
        yield TestClient(webapp.app)
    finally:
        webapp.app.dependency_overrides.pop(require_auth, None)
        webapp.app.dependency_overrides.pop(
            scheduling_router._scheduled_task_repository, None
        )
        webapp.app.dependency_overrides.pop(
            scheduling_router._task_scheduler_dependency, None
        )
        webapp.app.dependency_overrides.pop(
            scheduling_router._delivery_target_resolver, None
        )


def _as(user: User) -> None:
    webapp.app.dependency_overrides[require_auth] = lambda: user


def test_get_non_admin_returns_only_own_tasks(
    client: TestClient, repo: _FakeRepository
) -> None:
    """Unit-1 / REQ-001: não-admin vê só as tarefas com owner_user_key == 'web:<id>'."""
    asyncio.run(repo.save(_make_task(id_="t-a", owner="web:user-a")))
    asyncio.run(repo.save(_make_task(id_="t-b", owner="web:user-b")))

    _as(_USER_A)
    resp = client.get("/api/scheduled-tasks")

    assert resp.status_code == 200, resp.text
    ids = sorted(t["id"] for t in resp.json())
    assert ids == ["t-a"]


def test_get_admin_returns_all_tasks(client: TestClient, repo: _FakeRepository) -> None:
    """Unit-2 / REQ-001: admin vê todas as tarefas, independente do owner_user_key."""
    asyncio.run(repo.save(_make_task(id_="t-a", owner="web:user-a")))
    asyncio.run(repo.save(_make_task(id_="t-b", owner="web:user-b")))

    _as(_ADMIN)
    resp = client.get("/api/scheduled-tasks")

    assert resp.status_code == 200, resp.text
    ids = sorted(t["id"] for t in resp.json())
    assert ids == ["t-a", "t-b"]


def test_post_persists_owner_from_session_ignoring_body_field(
    client: TestClient, repo: _FakeRepository, scheduler: _FakeScheduler
) -> None:
    """Unit-3 / REQ-002: dono vem da sessão; campo do corpo é ignorado; trigger registrado."""
    _as(_USER_A)

    resp = client.post(
        "/api/scheduled-tasks",
        json={
            "prompt": "diga oi",
            "schedule_kind": "once",
            "schedule_expr": "2026-12-31T23:59:00",
            "owner_user_key": "web:someone-else",
        },
    )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["owner_user_key"] == "web:user-a"

    saved = repo._store[body["id"]]
    assert saved.owner_user_key == "web:user-a"
    assert scheduler.scheduled == [body["id"]]


def test_patch_owner_updates_scheduled_task(
    client: TestClient, repo: _FakeRepository
) -> None:
    """Unit-1 / REQ-003: dono edita a própria tarefa SCHEDULED → 200, campos atualizados."""
    asyncio.run(repo.save(_make_task(id_="t-a", owner="web:user-a")))
    _as(_USER_A)

    resp = client.patch("/api/scheduled-tasks/t-a", json={"prompt": "novo prompt"})

    assert resp.status_code == 200, resp.text
    assert resp.json()["prompt"] == "novo prompt"
    assert repo._store["t-a"].prompt == "novo prompt"


def test_patch_non_owner_non_admin_forbidden(
    client: TestClient, repo: _FakeRepository
) -> None:
    """Unit-2 / REQ-003: não-dono não-admin → 403, tarefa permanece inalterada."""
    asyncio.run(repo.save(_make_task(id_="t-a", owner="web:user-b")))
    _as(_USER_A)

    resp = client.patch("/api/scheduled-tasks/t-a", json={"prompt": "novo prompt"})

    assert resp.status_code == 403
    assert repo._store["t-a"].prompt == "x"


def test_patch_non_scheduled_task_rejected(
    client: TestClient, repo: _FakeRepository
) -> None:
    """Unit-3 / REQ-003: tarefa fora de SCHEDULED → 409/422, permanece inalterada."""
    task = _make_task(id_="t-a", owner="web:user-a")
    task.status = TaskStatus.RUNNING
    asyncio.run(repo.save(task))
    _as(_USER_A)

    resp = client.patch("/api/scheduled-tasks/t-a", json={"prompt": "novo prompt"})

    assert resp.status_code in (409, 422)
    assert repo._store["t-a"].prompt == "x"


def test_delete_owner_removes_task_and_unschedules(
    client: TestClient, repo: _FakeRepository, scheduler: _FakeScheduler
) -> None:
    """Unit-1 / REQ-004: dono exclui a própria tarefa → removida, trigger desagendado."""
    asyncio.run(repo.save(_make_task(id_="t-a", owner="web:user-a")))
    _as(_USER_A)

    resp = client.delete("/api/scheduled-tasks/t-a")

    assert resp.status_code == 204, resp.text
    assert "t-a" not in repo._store
    assert scheduler.unscheduled == ["t-a"]


def test_delete_non_owner_non_admin_forbidden(
    client: TestClient, repo: _FakeRepository
) -> None:
    """Unit-2 / REQ-004: não-dono não-admin → 403, tarefa não removida."""
    asyncio.run(repo.save(_make_task(id_="t-a", owner="web:user-b")))
    _as(_USER_A)

    resp = client.delete("/api/scheduled-tasks/t-a")

    assert resp.status_code == 403
    assert "t-a" in repo._store


def test_patch_ignores_client_supplied_ownership_and_admin_override(
    client: TestClient, repo: _FakeRepository
) -> None:
    """Unit-1 / REQ-005: campos de spoof no corpo do PATCH são ignorados — 403 persiste."""
    asyncio.run(repo.save(_make_task(id_="t-a", owner="web:user-b")))
    _as(_USER_A)

    resp = client.patch(
        "/api/scheduled-tasks/t-a",
        json={
            "prompt": "tentando escalar",
            "owner_user_key": "web:user-b",
            "is_admin": True,
        },
    )

    assert resp.status_code == 403
    assert repo._store["t-a"].prompt == "x"


def test_get_ignores_client_supplied_admin_query_param(
    client: TestClient, repo: _FakeRepository
) -> None:
    """Unit-1 / REQ-005: `?is_admin=true` na query string não eleva privilégio."""
    asyncio.run(repo.save(_make_task(id_="t-a", owner="web:user-a")))
    asyncio.run(repo.save(_make_task(id_="t-b", owner="web:user-b")))
    _as(_USER_A)

    resp = client.get("/api/scheduled-tasks?is_admin=true")

    assert resp.status_code == 200, resp.text
    ids = sorted(t["id"] for t in resp.json())
    assert ids == ["t-a"]


def test_post_with_delivery_channel_telegram_returns_resolved_key(
    client: TestClient,
    repo: _FakeRepository,
    integrations: _FakeIntegrationRepository,
    scheduler: _FakeScheduler,
) -> None:
    """api-1 unit-1 / REQ-004: POST com delivery_channel=telegram → delivery_user_key."""
    asyncio.run(
        integrations.save(
            _integration(
                id_="tg-a",
                user_id="user-a",
                integration_type="telegram",
                config={"chat_id": "4242"},
            )
        )
    )
    _as(_USER_A)

    resp = client.post(
        "/api/scheduled-tasks",
        json={
            "prompt": "mande no telegram",
            "schedule_kind": "once",
            "schedule_expr": "2026-12-31T23:59:00",
            "delivery_channel": "telegram",
        },
    )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["delivery_user_key"] == "telegram:4242"
    assert repo._store[body["id"]].delivery_user_key == "telegram:4242"
    assert scheduler.scheduled == [body["id"]]

    listed = client.get("/api/scheduled-tasks")
    assert listed.status_code == 200
    match = next(t for t in listed.json() if t["id"] == body["id"])
    assert match["delivery_user_key"] == "telegram:4242"


def test_post_delivery_channel_without_link_returns_4xx_without_creating(
    client: TestClient, repo: _FakeRepository, scheduler: _FakeScheduler
) -> None:
    """REQ-002: canal sem vínculo → 4xx; nada persistido / agendado."""
    _as(_USER_A)

    resp = client.post(
        "/api/scheduled-tasks",
        json={
            "prompt": "x",
            "schedule_kind": "once",
            "schedule_expr": "2026-12-31T23:59:00",
            "delivery_channel": "whatsapp",
        },
    )

    assert resp.status_code == 422
    assert repo._store == {}
    assert scheduler.scheduled == []


def test_get_delivery_channels_includes_web_and_caller_whatsapp_only(
    client: TestClient, integrations: _FakeIntegrationRepository
) -> None:
    """api-1 unit-2 / REQ-004: GET delivery-channels só do próprio user (+ web)."""
    asyncio.run(
        integrations.save(
            _integration(
                id_="wa-a",
                user_id="user-a",
                integration_type="whatsapp_business",
                config={"phone_number": "5511999999999"},
            )
        )
    )
    asyncio.run(
        integrations.save(
            _integration(
                id_="tg-b",
                user_id="user-b",
                integration_type="telegram",
                config={"chat_id": "99"},
            )
        )
    )
    _as(_USER_A)

    resp = client.get("/api/scheduling/delivery-channels")

    assert resp.status_code == 200, resp.text
    assert resp.json()["channels"] == ["web", "whatsapp"]


def test_to_response_includes_notify_status_and_error() -> None:
    """api-1 unit-1: serializador HTTP expõe notify_status / notify_error."""
    from src.infrastructure.web.scheduling_router import _to_response

    task = _make_task(id_="t-notify", owner="web:user-a")
    task.start()
    task.succeed()
    task.mark_notify_skipped("output_missing")

    body = _to_response(task).model_dump()

    assert body["notify_status"] == "skipped"
    assert body["notify_error"] == "output_missing"
    assert body["status"] == "succeeded"
