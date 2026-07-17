"""Testes de `src/infrastructure/auth/dependencies.py` (`require_auth`, `require_admin`).

Cobre REQ-002/REQ-003 de `backend-session-auth` e REQ-002/REQ-003 de
`rbac-user-roles` (change `autenticacao-jwt-rotas-protegidas`, task-rest-3).

`require_auth` é um wrapper fino sobre `session_resolver.resolve_session_user`
(testado em detalhe em `test_session_resolver.py`) que traduz `SessionAuthError`
para `fastapi.HTTPException(401)`. Aqui testamos só essa tradução e a
composição de `require_admin` sobre `require_auth`.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from src.infrastructure.auth import dependencies
from src.infrastructure.auth.dependencies import require_admin, require_auth
from src.infrastructure.auth.session_resolver import SessionAuthError
from src.infrastructure.auth.users import User

_ADMIN_USER = User(id="user-1", username="alice", password_hash="h", role="admin", is_active=True)
_REGULAR_USER = User(id="user-2", username="bob", password_hash="h", role="user", is_active=True)


def _request(path: str) -> Request:
    scope = {"type": "http", "method": "GET", "path": path, "headers": [], "query_string": b""}
    return Request(scope)


# --- require_auth: tradução de SessionAuthError para HTTPException ----------


async def test_require_auth_translates_session_auth_error_to_401(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _raise(request: Request) -> User | None:
        raise SessionAuthError("missing session cookie")

    monkeypatch.setattr(dependencies, "resolve_session_user", _raise)

    with pytest.raises(HTTPException) as exc_info:
        await require_auth(_request("/api/images"))

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Unauthorized"


async def test_require_auth_passes_through_resolved_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _resolve(request: Request) -> User | None:
        return _ADMIN_USER

    monkeypatch.setattr(dependencies, "resolve_session_user", _resolve)

    result = await require_auth(_request("/api/images"))

    assert result == _ADMIN_USER


async def test_require_auth_passes_through_none_for_public_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PUBLIC_PATHS", raising=False)

    result = await require_auth(_request("/public/login"))

    assert result is None


# --- rbac-user-roles REQ-002/REQ-003: require_admin -------------------------


async def test_require_admin_allows_admin_role() -> None:
    result = await require_admin(_ADMIN_USER)

    assert result == _ADMIN_USER


async def test_require_admin_rejects_user_role_with_403() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await require_admin(_REGULAR_USER)

    assert exc_info.value.status_code == 403


async def test_require_admin_rejects_unauthenticated_with_401() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await require_admin(None)

    assert exc_info.value.status_code == 401
