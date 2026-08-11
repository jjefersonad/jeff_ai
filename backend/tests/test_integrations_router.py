"""Testes de `GET`/`POST /api/integrations`, `GET`/`PUT`/`DELETE /api/integrations/{id}`
(task `user-integration-credentials-task-api-1`).

Cobre os 3 unit-tests linkados à task no OpenSddRag:

- unit-1 (REQ-001): requisição sem sessão válida é rejeitada (401) antes de
  alcançar qualquer caso de uso.
- unit-2 (REQ-001): dono autenticado faz POST e depois GET, vendo a própria
  entrada com os valores corretos.
- unit-3 (REQ-001): não-dono não-admin em GET/PUT/DELETE de uma entrada de
  outro usuário recebe rejeição, sem revelar dado alheio.

Persistência é um fake injetado via override de dependency, mesmo padrão de
`test_scheduling_router.py`.
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timezone

import pytest
from fastapi.testclient import TestClient

import src.infrastructure.web.integrations_router as integrations_router
import src.infrastructure.web.webapp as webapp
from src.application.ports.user_integration_repository import (
    UserIntegrationRepositoryPort,
)
from src.domain.integrations import UserIntegration
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
_USER_B = User(
    id="user-b",
    username="carol",
    password_hash="h",
    role="user",
    is_active=True,
    created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
)


class _FakeRepository(UserIntegrationRepositoryPort):
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


def _make_integration(*, id_: str, user_id: str) -> UserIntegration:
    return UserIntegration(
        id=id_,
        user_id=user_id,
        integration_type="telegram",
        config={"chat_id": "123"},
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


@pytest.fixture
def repo() -> _FakeRepository:
    return _FakeRepository()


@pytest.fixture
def client(repo: _FakeRepository):
    """Cliente do webapp com repo/auth sobrescritos pelo teste."""
    webapp.app.dependency_overrides[
        integrations_router._user_integration_repository
    ] = lambda: repo
    try:
        yield TestClient(webapp.app)
    finally:
        webapp.app.dependency_overrides.pop(require_auth, None)
        webapp.app.dependency_overrides.pop(
            integrations_router._user_integration_repository, None
        )


def _as(user: User) -> None:
    webapp.app.dependency_overrides[require_auth] = lambda: user


# ===========================================================================
# unit-1 (REQ-001): sem sessão válida -> 401
# ===========================================================================


def test_list_without_session_is_unauthorized(client: TestClient) -> None:
    """Sem cookie de sessão, `require_auth` (dependency global) já rejeita com 401."""
    resp = client.get("/api/integrations")

    assert resp.status_code == 401


def test_create_without_session_is_unauthorized(client: TestClient) -> None:
    resp = client.post(
        "/api/integrations", json={"integration_type": "telegram", "config": {"chat_id": "1"}}
    )

    assert resp.status_code == 401


# ===========================================================================
# unit-2 (REQ-001): round-trip POST -> GET para o dono
# ===========================================================================


def test_owner_post_then_get_round_trip(client: TestClient, repo: _FakeRepository) -> None:
    _as(_USER_A)

    create_resp = client.post(
        "/api/integrations",
        json={"integration_type": "telegram", "config": {"chat_id": "999"}},
    )
    assert create_resp.status_code == 201, create_resp.text
    created = create_resp.json()
    assert created["user_id"] == "user-a"
    assert created["config"] == {"chat_id": "999"}

    get_resp = client.get(f"/api/integrations/{created['id']}")

    assert get_resp.status_code == 200, get_resp.text
    body = get_resp.json()
    assert body["id"] == created["id"]
    assert body["config"] == {"chat_id": "999"}
    assert body["user_id"] == "user-a"


def test_owner_sees_own_entry_in_list(client: TestClient, repo: _FakeRepository) -> None:
    asyncio.run(repo.save(_make_integration(id_="i-a", user_id="user-a")))
    _as(_USER_A)

    resp = client.get("/api/integrations")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body) == 1
    assert body[0]["config"] == {"chat_id": "123"}


def test_admin_list_hides_other_users_config() -> None:
    """REQ-004 scenario 1: admin GET na listagem nunca traz config decifrado alheio."""
    repo = _FakeRepository()
    asyncio.run(repo.save(_make_integration(id_="i-a", user_id="user-a")))
    webapp.app.dependency_overrides[
        integrations_router._user_integration_repository
    ] = lambda: repo
    _as(_ADMIN)

    try:
        client = TestClient(webapp.app)
        resp = client.get("/api/integrations")

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body[0]["user_id"] == "user-a"
        assert body[0]["config"] is None
    finally:
        webapp.app.dependency_overrides.pop(require_auth, None)
        webapp.app.dependency_overrides.pop(
            integrations_router._user_integration_repository, None
        )


# ===========================================================================
# unit-3 (REQ-001): não-dono não-admin em GET/PUT/DELETE de entrada alheia
# ===========================================================================


def test_get_cross_user_entry_is_not_found(client: TestClient, repo: _FakeRepository) -> None:
    asyncio.run(repo.save(_make_integration(id_="i-b", user_id="user-b")))
    _as(_USER_A)

    resp = client.get("/api/integrations/i-b")

    assert resp.status_code == 404


def test_put_cross_user_entry_is_not_found(client: TestClient, repo: _FakeRepository) -> None:
    asyncio.run(repo.save(_make_integration(id_="i-b", user_id="user-b")))
    _as(_USER_A)

    resp = client.put(
        "/api/integrations/i-b",
        json={"integration_type": "telegram", "config": {"chat_id": "hacked"}},
    )

    assert resp.status_code == 404
    assert repo._store["i-b"].config == {"chat_id": "123"}


def test_delete_cross_user_entry_is_silent_noop(
    client: TestClient, repo: _FakeRepository
) -> None:
    asyncio.run(repo.save(_make_integration(id_="i-b", user_id="user-b")))
    _as(_USER_A)

    resp = client.delete("/api/integrations/i-b")

    assert resp.status_code == 204
    assert "i-b" in repo._store


def test_owner_put_updates_own_entry(client: TestClient, repo: _FakeRepository) -> None:
    asyncio.run(repo.save(_make_integration(id_="i-a", user_id="user-a")))
    _as(_USER_A)

    resp = client.put(
        "/api/integrations/i-a",
        json={"integration_type": "telegram", "config": {"chat_id": "new"}},
    )

    assert resp.status_code == 200, resp.text
    assert repo._store["i-a"].config == {"chat_id": "new"}


def test_owner_delete_removes_own_entry(client: TestClient, repo: _FakeRepository) -> None:
    asyncio.run(repo.save(_make_integration(id_="i-a", user_id="user-a")))
    _as(_USER_A)

    resp = client.delete("/api/integrations/i-a")

    assert resp.status_code == 204
    assert "i-a" not in repo._store


def test_create_rejects_invalid_config_for_integration_type(client: TestClient) -> None:
    """REQ-003: payload fora do schema do `integration_type` é rejeitado (422)."""
    _as(_USER_A)

    resp = client.post(
        "/api/integrations", json={"integration_type": "telegram", "config": {}}
    )

    assert resp.status_code == 422


# ===========================================================================
# GET /api/integrations/channel-config (channel-link-wiring-task-config-endpoint-1)
# ===========================================================================


def test_channel_config_returns_configured_values(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Unit 'channel-config returns configured values' (channel-link-deep-links REQ-002)."""
    monkeypatch.setenv("TELEGRAM_BOT_USERNAME", "jeff_ai_bot")
    monkeypatch.setenv("WHATSAPP_BUSINESS_NUMBER", "5511999999999")
    _as(_USER_A)

    resp = client.get("/api/integrations/channel-config")

    assert resp.status_code == 200
    assert resp.json() == {
        "telegram_bot_username": "jeff_ai_bot",
        "whatsapp_business_number": "5511999999999",
    }


def test_channel_config_requires_auth(client: TestClient) -> None:
    """Unit 'channel-config requires auth' (channel-link-deep-links REQ-002)."""
    resp = client.get("/api/integrations/channel-config")

    assert resp.status_code == 401


def test_channel_config_nulls_unset_values(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Unit 'channel-config nulls unset values' (channel-link-deep-links REQ-002)."""
    monkeypatch.delenv("TELEGRAM_BOT_USERNAME", raising=False)
    monkeypatch.delenv("WHATSAPP_BUSINESS_NUMBER", raising=False)
    _as(_USER_A)

    resp = client.get("/api/integrations/channel-config")

    assert resp.status_code == 200
    assert resp.json() == {
        "telegram_bot_username": None,
        "whatsapp_business_number": None,
    }
