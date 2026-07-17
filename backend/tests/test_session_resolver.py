"""Testes de `src/infrastructure/auth/session_resolver.py` (`resolve_session_user`).

Núcleo compartilhado por `dependencies.require_auth` (FastAPI, task-rest-3) e
`web.auth.authenticate` (handler nativo do LangGraph, task-langgraph-auth-1) —
ver REQ-003 de `langgraph-native-auth-middleware` ("mesmo modelo de sessão").
Cobre também REQ-002/REQ-003 de `backend-session-auth` e a exceção de
`PUBLIC_PATHS` de `backend-api-routes-delta` REQ-003.

Testes de unidade: monkeypatcham `get_session`/`get_user_by_id` diretamente
no módulo, sem tocar em Postgres real.
"""
from __future__ import annotations

import pytest
from starlette.requests import Request

from src.infrastructure.auth import session_resolver
from src.infrastructure.auth.session_resolver import (
    SessionAuthError,
    resolve_session_user,
)
from src.infrastructure.auth.sessions import Session
from src.infrastructure.auth.users import User

_VALID_SESSION = Session(token="tok", user_id="user-1", expires_at=None)  # type: ignore[arg-type]
_ADMIN_USER = User(id="user-1", username="alice", password_hash="h", role="admin", is_active=True)


def _request(path: str, cookie: str | None = None) -> Request:
    headers = []
    if cookie is not None:
        headers.append((b"cookie", f"session={cookie}".encode()))
    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "headers": headers,
        "query_string": b"",
    }
    return Request(scope)


# --- PUBLIC_PATHS -----------------------------------------------------------


async def test_resolve_session_user_allows_public_path_without_cookie(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PUBLIC_PATHS", raising=False)

    result = await resolve_session_user(_request("/public/login"))

    assert result is None


async def test_resolve_session_user_respects_public_paths_env_var(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PUBLIC_PATHS", "/public/,/health")

    result = await resolve_session_user(_request("/health"))

    assert result is None


# --- REQ-002/REQ-003: sessão ausente/desconhecida/expirada -----------------


async def test_resolve_session_user_rejects_missing_cookie(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PUBLIC_PATHS", raising=False)

    with pytest.raises(SessionAuthError):
        await resolve_session_user(_request("/api/images"))


async def test_resolve_session_user_rejects_unknown_or_expired_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PUBLIC_PATHS", raising=False)

    async def _fake_get_session(token: str) -> Session | None:
        return None

    monkeypatch.setattr(session_resolver, "get_session", _fake_get_session)

    with pytest.raises(SessionAuthError):
        await resolve_session_user(_request("/api/images", cookie="unknown-tok"))


async def test_resolve_session_user_rejects_session_of_inactive_or_deleted_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PUBLIC_PATHS", raising=False)

    async def _fake_get_session(token: str) -> Session | None:
        return _VALID_SESSION

    async def _fake_get_user_by_id(user_id: str) -> User | None:
        return None

    monkeypatch.setattr(session_resolver, "get_session", _fake_get_session)
    monkeypatch.setattr(session_resolver, "get_user_by_id", _fake_get_user_by_id)

    with pytest.raises(SessionAuthError):
        await resolve_session_user(_request("/api/images", cookie="tok"))


async def test_resolve_session_user_returns_user_for_valid_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PUBLIC_PATHS", raising=False)

    async def _fake_get_session(token: str) -> Session | None:
        return _VALID_SESSION

    async def _fake_get_user_by_id(user_id: str) -> User | None:
        return _ADMIN_USER

    monkeypatch.setattr(session_resolver, "get_session", _fake_get_session)
    monkeypatch.setattr(session_resolver, "get_user_by_id", _fake_get_user_by_id)

    result = await resolve_session_user(_request("/api/images", cookie="tok"))

    assert result == _ADMIN_USER
