"""Testes de `src/infrastructure/auth/sessions.py` (gestão de sessões)."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from src.infrastructure.auth import sessions


class _FakeCursor:
    def __init__(self, fetchone_result: tuple | None = None) -> None:
        self.executed: list[tuple[str, tuple | None]] = []
        self._fetchone_result = fetchone_result

    async def __aenter__(self) -> "_FakeCursor":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return None

    async def execute(self, query: str, params: tuple | None = None) -> None:
        self.executed.append((query, params))

    async def fetchone(self) -> tuple | None:
        return self._fetchone_result


class _FakeConnection:
    def __init__(self, cursor: _FakeCursor) -> None:
        self._cursor = cursor

    async def __aenter__(self) -> "_FakeConnection":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return None

    def cursor(self) -> _FakeCursor:
        return self._cursor


class _FakePool:
    def __init__(self, cursor: _FakeCursor) -> None:
        self._cursor = cursor

    def connection(self) -> _FakeConnection:
        return _FakeConnection(self._cursor)


def _patch_pool(monkeypatch: pytest.MonkeyPatch, cursor: _FakeCursor) -> None:
    monkeypatch.setattr(sessions, "get_pool", lambda: _FakePool(cursor))


async def test_create_session_generates_high_entropy_token(monkeypatch: pytest.MonkeyPatch) -> None:
    cursor = _FakeCursor()
    _patch_pool(monkeypatch, cursor)
    monkeypatch.delenv("SESSION_TTL", raising=False)

    token = await sessions.create_session("user-1")

    assert len(token) >= 32
    query, params = cursor.executed[0]
    assert "INSERT INTO sessions" in query
    assert params is not None
    assert params[0] == token
    assert params[1] == "user-1"


async def test_create_session_defaults_ttl_to_one_hour(monkeypatch: pytest.MonkeyPatch) -> None:
    cursor = _FakeCursor()
    _patch_pool(monkeypatch, cursor)
    monkeypatch.delenv("SESSION_TTL", raising=False)

    before = datetime.now(UTC)
    await sessions.create_session("user-1")

    _, params = cursor.executed[0]
    assert params is not None
    expires_at = params[2]
    assert timedelta(seconds=3500) < (expires_at - before) < timedelta(seconds=3700)


async def test_create_session_respects_session_ttl_env(monkeypatch: pytest.MonkeyPatch) -> None:
    cursor = _FakeCursor()
    _patch_pool(monkeypatch, cursor)
    monkeypatch.setenv("SESSION_TTL", "60")

    before = datetime.now(UTC)
    await sessions.create_session("user-1")

    _, params = cursor.executed[0]
    assert params is not None
    expires_at = params[2]
    assert (expires_at - before) < timedelta(seconds=65)


async def test_get_session_returns_none_when_not_found_or_expired(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cursor = _FakeCursor(fetchone_result=None)
    _patch_pool(monkeypatch, cursor)

    result = await sessions.get_session("unknown-or-expired-token")

    assert result is None
    query, _ = cursor.executed[0]
    assert "expires_at > now()" in query


async def test_get_session_returns_session_when_valid(monkeypatch: pytest.MonkeyPatch) -> None:
    expires_at = datetime.now(UTC) + timedelta(hours=1)
    cursor = _FakeCursor(fetchone_result=("tok", "user-1", expires_at))
    _patch_pool(monkeypatch, cursor)

    result = await sessions.get_session("tok")

    assert result == sessions.Session(token="tok", user_id="user-1", expires_at=expires_at)


async def test_revoke_session_deletes_row_immediately(monkeypatch: pytest.MonkeyPatch) -> None:
    cursor = _FakeCursor()
    _patch_pool(monkeypatch, cursor)

    await sessions.revoke_session("tok")

    query, params = cursor.executed[0]
    assert "DELETE FROM sessions" in query
    assert params == ("tok",)
