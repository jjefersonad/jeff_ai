"""Testes de `auth_router` (`POST /public/login`, `POST /public/logout`).

Cobre REQ-001 e REQ-004 de `backend-session-auth` e REQ-003 de
`public-endpoints` (change `autenticacao-jwt-rotas-protegidas`, task-rest-1).

Monkeypatcha as dependências (`get_user_by_username`, `verify_password`,
`create_session`, `revoke_session`) diretamente no módulo `auth_router` —
mesmo padrão de isolamento usado em `test_auth_sessions.py` — para não exigir
Postgres real nem disparar o `lifespan` completo de `webapp.py`.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import src.infrastructure.web.auth_router as auth_router
import src.infrastructure.web.webapp as webapp
from src.infrastructure.auth.users import User


@pytest.fixture
def client() -> TestClient:
    """Cliente FastAPI para o `webapp.app` (sem subir o servidor real)."""
    return TestClient(webapp.app)


_ACTIVE_USER = User(
    id="user-1",
    username="alice",
    password_hash="hashed",
    role="admin",
    is_active=True,
)


def _patch_login(
    monkeypatch: pytest.MonkeyPatch,
    *,
    user: User | None,
    password_ok: bool,
    token: str = "tok-123",
) -> list[str]:
    created_for: list[str] = []

    async def _fake_get_user_by_username(username: str) -> User | None:
        return user

    def _fake_verify_password(plain: str, hashed: str) -> bool:
        return password_ok

    async def _fake_create_session(user_id: str) -> str:
        created_for.append(user_id)
        return token

    monkeypatch.setattr(auth_router, "get_user_by_username", _fake_get_user_by_username)
    monkeypatch.setattr(auth_router, "verify_password", _fake_verify_password)
    monkeypatch.setattr(auth_router, "create_session", _fake_create_session)
    return created_for


# --- REQ-001: login -------------------------------------------------------


def test_login_with_valid_credentials_sets_session_cookie(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    created_for = _patch_login(monkeypatch, user=_ACTIVE_USER, password_ok=True, token="tok-abc")

    response = client.post("/public/login", json={"username": "alice", "password": "s3cr3t"})

    assert response.status_code == 200
    assert created_for == ["user-1"]
    cookie = response.cookies.get("session")
    assert cookie == "tok-abc"


def test_login_with_wrong_password_returns_401_without_creating_session(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    created_for = _patch_login(monkeypatch, user=_ACTIVE_USER, password_ok=False)

    response = client.post("/public/login", json={"username": "alice", "password": "wrong"})

    assert response.status_code == 401
    assert response.json() == {"detail": "Unauthorized"}
    assert created_for == []
    assert "session" not in response.cookies


def test_login_with_unknown_username_returns_401_without_creating_session(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    created_for = _patch_login(monkeypatch, user=None, password_ok=True)

    response = client.post("/public/login", json={"username": "ghost", "password": "whatever"})

    assert response.status_code == 401
    assert response.json() == {"detail": "Unauthorized"}
    assert created_for == []


def test_login_with_inactive_user_returns_401_without_creating_session(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    inactive_user = User(id="user-2", username="bob", password_hash="h", role="user", is_active=False)
    created_for = _patch_login(monkeypatch, user=inactive_user, password_ok=True)

    response = client.post("/public/login", json={"username": "bob", "password": "whatever"})

    assert response.status_code == 401
    assert created_for == []


# --- REQ-004: logout -------------------------------------------------------


def test_logout_revokes_session_and_clears_cookie(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    revoked: list[str] = []

    async def _fake_revoke_session(token: str) -> None:
        revoked.append(token)

    monkeypatch.setattr(auth_router, "revoke_session", _fake_revoke_session)
    client.cookies.set("session", "tok-to-revoke")

    response = client.post("/public/logout")

    assert response.status_code == 200
    assert revoked == ["tok-to-revoke"]
    assert response.cookies.get("session") is None


def test_logout_without_cookie_is_a_noop_and_clears_cookie(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    revoked: list[str] = []

    async def _fake_revoke_session(token: str) -> None:
        revoked.append(token)

    monkeypatch.setattr(auth_router, "revoke_session", _fake_revoke_session)

    response = client.post("/public/logout")

    assert response.status_code == 200
    assert revoked == []
