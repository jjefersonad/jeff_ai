"""Testes de `src/infrastructure/auth/users.py` (leitura de usuários)."""
from __future__ import annotations

import pytest

from src.infrastructure.auth import users


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
    monkeypatch.setattr(users, "get_pool", lambda: _FakePool(cursor))


async def test_get_user_by_username_returns_none_when_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cursor = _FakeCursor(fetchone_result=None)
    _patch_pool(monkeypatch, cursor)

    result = await users.get_user_by_username("ghost")

    assert result is None
    query, params = cursor.executed[0]
    assert "SELECT" in query
    assert "FROM users" in query
    assert params == ("ghost",)


async def test_get_user_by_username_returns_user_when_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cursor = _FakeCursor(fetchone_result=("id-1", "alice", "hashed-pw", "admin", True))
    _patch_pool(monkeypatch, cursor)

    result = await users.get_user_by_username("alice")

    assert result == users.User(
        id="id-1", username="alice", password_hash="hashed-pw", role="admin", is_active=True
    )
