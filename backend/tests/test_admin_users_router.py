"""Testes de `admin_users_router` (change `user-management`).

Router montado isoladamente (sem subir o `webapp.app` inteiro), com
`require_admin` sobrescrito via `dependency_overrides` — mesmo padrão de
`test_mcp_admin_api.py`. `list_users`/`create_user` são mockados para nunca
tocar o Postgres real.

Cobre `user-management-api-spec`:
- REQ-001: `GET /admin/users` devolve todos os usuários (sem `password_hash`)
  para `role=admin`, e 403 para `role=user`.
- REQ-002 (task-api-2): `POST /admin/users` com senha válida cria o usuário
  (hash bcrypt, nunca a senha em texto plano) e retorna 201; com senha curta
  demais retorna 422 sem criar o usuário.
- REQ-003 (task-api-3): `PATCH /admin/users/{id}` atualiza `role`/`is_active`
  de outro usuário e retorna 200. A tradução do guarda-corpo de auto-lockout
  (`SelfLockoutError`/`LastAdminError`) para 409 é escopo de task-api-4, não
  testada aqui.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.infrastructure.auth.dependencies import require_admin
from src.infrastructure.auth.users import User
from src.infrastructure.web import admin_users_router

_ADMIN = User(
    id="admin-1",
    username="admin",
    password_hash="h",
    role="admin",
    is_active=True,
    created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
)

_NON_ADMIN = User(
    id="user-1",
    username="alice",
    password_hash="h",
    role="user",
    is_active=True,
    created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
)

_USERS_ROWS = [
    User(
        id="admin-1",
        username="admin",
        password_hash="super-secret-hash",
        role="admin",
        is_active=True,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    ),
    User(
        id="user-1",
        username="alice",
        password_hash="another-secret-hash",
        role="user",
        is_active=False,
        created_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
    ),
]


_CREATED_USER = User(
    id="new-user-1",
    username="newbie",
    password_hash="bcrypt-hash-of-supersecret",
    role="user",
    is_active=True,
    created_at=datetime(2026, 1, 3, tzinfo=timezone.utc),
)


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(
        admin_users_router, "list_users", AsyncMock(return_value=_USERS_ROWS)
    )
    monkeypatch.setattr(
        admin_users_router, "create_user", AsyncMock(return_value=_CREATED_USER)
    )
    app = FastAPI()
    app.include_router(admin_users_router.router)
    return TestClient(app)


def test_get_admin_users_as_admin_returns_users_without_password_hash(
    client: TestClient,
) -> None:
    client.app.dependency_overrides[require_admin] = lambda: _ADMIN
    try:
        response = client.get("/admin/users")
    finally:
        client.app.dependency_overrides.pop(require_admin, None)

    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"users"}
    assert len(body["users"]) == 2
    for entry, expected in zip(body["users"], _USERS_ROWS, strict=True):
        assert set(entry.keys()) == {"id", "username", "role", "is_active", "created_at"}
        assert entry["id"] == expected.id
        assert entry["username"] == expected.username
        assert entry["role"] == expected.role
        assert entry["is_active"] == expected.is_active
    assert "password_hash" not in response.text
    assert "super-secret-hash" not in response.text
    assert "another-secret-hash" not in response.text


def test_get_admin_users_as_non_admin_returns_403(client: TestClient) -> None:
    from fastapi import HTTPException

    async def _forbidden() -> User:
        raise HTTPException(status_code=403, detail="Forbidden")

    client.app.dependency_overrides[require_admin] = _forbidden
    try:
        response = client.get("/admin/users")
    finally:
        client.app.dependency_overrides.pop(require_admin, None)

    assert response.status_code == 403
    admin_users_router.list_users.assert_not_called()


def test_post_admin_users_with_valid_password_creates_user_and_returns_201(
    client: TestClient,
) -> None:
    client.app.dependency_overrides[require_admin] = lambda: _ADMIN
    try:
        response = client.post(
            "/admin/users",
            json={"username": "newbie", "password": "supersecret", "role": "user"},
        )
    finally:
        client.app.dependency_overrides.pop(require_admin, None)

    assert response.status_code == 201
    body = response.json()
    assert set(body.keys()) == {"id", "username", "role", "is_active", "created_at"}
    assert body["username"] == "newbie"
    assert body["role"] == "user"
    assert "password" not in response.text
    assert "password_hash" not in response.text
    assert "bcrypt-hash-of-supersecret" not in response.text

    admin_users_router.create_user.assert_awaited_once()
    _args, kwargs = admin_users_router.create_user.await_args
    assert kwargs["username"] == "newbie"
    assert kwargs["password_hash"] != "supersecret"  # nunca a senha em texto plano
    assert kwargs["role"] == "user"


def test_post_admin_users_with_short_password_returns_422_and_creates_nothing(
    client: TestClient,
) -> None:
    client.app.dependency_overrides[require_admin] = lambda: _ADMIN
    try:
        response = client.post(
            "/admin/users",
            json={"username": "newbie", "password": "short12", "role": "user"},
        )
    finally:
        client.app.dependency_overrides.pop(require_admin, None)

    assert response.status_code == 422
    admin_users_router.create_user.assert_not_called()


def test_post_admin_users_defaults_role_to_user(client: TestClient) -> None:
    client.app.dependency_overrides[require_admin] = lambda: _ADMIN
    try:
        client.post(
            "/admin/users",
            json={"username": "newbie", "password": "supersecret"},
        )
    finally:
        client.app.dependency_overrides.pop(require_admin, None)

    _args, kwargs = admin_users_router.create_user.await_args
    assert kwargs["role"] == "user"


_PATCHED_USER = User(
    id="user-1",
    username="alice",
    password_hash="another-secret-hash",
    role="admin",
    is_active=True,
    created_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
)


def test_patch_admin_users_updates_role_and_returns_200(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        admin_users_router, "update_user", AsyncMock(return_value=_PATCHED_USER)
    )
    client.app.dependency_overrides[require_admin] = lambda: _ADMIN
    try:
        response = client.patch("/admin/users/user-1", json={"role": "admin"})
    finally:
        client.app.dependency_overrides.pop(require_admin, None)

    assert response.status_code == 200
    body = response.json()
    assert body["role"] == "admin"
    assert "password_hash" not in response.text

    admin_users_router.update_user.assert_awaited_once()
    _args, kwargs = admin_users_router.update_user.await_args
    assert kwargs["role"] == "admin"
    assert kwargs["is_active"] is None
    assert kwargs["caller_id"] == _ADMIN.id


def test_patch_admin_users_deactivates_and_returns_200(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    deactivated = User(
        id="user-1",
        username="alice",
        password_hash="another-secret-hash",
        role="user",
        is_active=False,
        created_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
    )
    monkeypatch.setattr(
        admin_users_router, "update_user", AsyncMock(return_value=deactivated)
    )
    client.app.dependency_overrides[require_admin] = lambda: _ADMIN
    try:
        response = client.patch("/admin/users/user-1", json={"is_active": False})
    finally:
        client.app.dependency_overrides.pop(require_admin, None)

    assert response.status_code == 200
    assert response.json()["is_active"] is False

    _args, kwargs = admin_users_router.update_user.await_args
    assert kwargs["is_active"] is False
    assert kwargs["role"] is None


def test_patch_admin_users_self_lockout_returns_409(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """REQ-004 (task-api-4): `update_user` recusa via `SelfLockoutError` -> 409, sem 500."""
    from src.infrastructure.auth.users import SelfLockoutError

    async def _raise_self_lockout(*args: object, **kwargs: object) -> User:
        raise SelfLockoutError("nope")

    monkeypatch.setattr(admin_users_router, "update_user", _raise_self_lockout)
    client.app.dependency_overrides[require_admin] = lambda: _ADMIN
    try:
        response = client.patch(f"/admin/users/{_ADMIN.id}", json={"is_active": False})
    finally:
        client.app.dependency_overrides.pop(require_admin, None)

    assert response.status_code == 409


def test_patch_admin_users_last_admin_lockout_returns_409(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """REQ-004 (task-api-4): `update_user` recusa via `LastAdminError` -> 409, sem 500."""
    from src.infrastructure.auth.users import LastAdminError

    async def _raise_last_admin(*args: object, **kwargs: object) -> User:
        raise LastAdminError("nope")

    monkeypatch.setattr(admin_users_router, "update_user", _raise_last_admin)
    client.app.dependency_overrides[require_admin] = lambda: _ADMIN
    try:
        response = client.patch("/admin/users/user-1", json={"is_active": False})
    finally:
        client.app.dependency_overrides.pop(require_admin, None)

    assert response.status_code == 409
