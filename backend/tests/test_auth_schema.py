"""Testes de `src/infrastructure/auth/schema.py` (schema + bootstrap do admin)."""
from __future__ import annotations

import pytest

from src.infrastructure.auth import schema


class _FakeCursor:
    def __init__(self, users_count: int) -> None:
        self.users_count = users_count
        self.executed: list[tuple[str, tuple | None]] = []

    def __enter__(self) -> "_FakeCursor":
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None

    def execute(self, query: str, params: tuple | None = None) -> None:
        self.executed.append((query, params))

    def fetchone(self) -> tuple[int]:
        return (self.users_count,)


class _FakeConnection:
    def __init__(self, users_count: int = 0) -> None:
        self._cursor = _FakeCursor(users_count)

    def __enter__(self) -> "_FakeConnection":
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None

    def cursor(self) -> _FakeCursor:
        return self._cursor


def test_ensure_schema_creates_users_and_sessions_tables(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_conn = _FakeConnection()
    monkeypatch.setattr(schema.psycopg, "connect", lambda *a, **kw: fake_conn)

    schema.ensure_schema("postgresql://fake")

    executed_sql = "\n".join(q for q, _ in fake_conn._cursor.executed)
    assert "CREATE TABLE IF NOT EXISTS users" in executed_sql
    assert "CREATE TABLE IF NOT EXISTS sessions" in executed_sql
    assert "CHECK (role IN ('admin', 'user'))" in executed_sql


def test_bootstrap_admin_noop_when_users_exist(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_conn = _FakeConnection(users_count=1)
    monkeypatch.setattr(schema.psycopg, "connect", lambda *a, **kw: fake_conn)
    monkeypatch.delenv("ADMIN_USERNAME", raising=False)
    monkeypatch.delenv("ADMIN_PASSWORD_HASH", raising=False)

    schema.bootstrap_admin("postgresql://fake")

    inserts = [q for q, _ in fake_conn._cursor.executed if q.strip().startswith("INSERT")]
    assert inserts == []


def test_bootstrap_admin_creates_admin_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_conn = _FakeConnection(users_count=0)
    monkeypatch.setattr(schema.psycopg, "connect", lambda *a, **kw: fake_conn)
    monkeypatch.setenv("ADMIN_USERNAME", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", "$2b$12$fakehash")

    schema.bootstrap_admin("postgresql://fake")

    inserts = [(q, p) for q, p in fake_conn._cursor.executed if q.strip().startswith("INSERT")]
    assert len(inserts) == 1
    query, params = inserts[0]
    assert "INSERT INTO users" in query
    assert params == ("admin", "$2b$12$fakehash")


def test_bootstrap_admin_raises_when_env_missing_and_users_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_conn = _FakeConnection(users_count=0)
    monkeypatch.setattr(schema.psycopg, "connect", lambda *a, **kw: fake_conn)
    monkeypatch.delenv("ADMIN_USERNAME", raising=False)
    monkeypatch.delenv("ADMIN_PASSWORD_HASH", raising=False)

    with pytest.raises(schema.AuthBootstrapError):
        schema.bootstrap_admin("postgresql://fake")


def test_init_auth_schema_runs_ensure_schema_then_bootstrap(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(schema, "ensure_schema", lambda conninfo: calls.append("ensure"))
    monkeypatch.setattr(schema, "bootstrap_admin", lambda conninfo: calls.append("bootstrap"))

    schema.init_auth_schema("postgresql://fake")

    assert calls == ["ensure", "bootstrap"]
