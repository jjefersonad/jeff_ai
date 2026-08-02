"""Testes de `src/infrastructure/usage/schema.py` (tabela `token_usage_events`)."""
from __future__ import annotations

import pytest

from src.infrastructure.usage import schema


class _FakeCursor:
    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple | None]] = []

    def __enter__(self) -> "_FakeCursor":
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None

    def execute(self, query: str, params: tuple | None = None) -> None:
        self.executed.append((query, params))


class _FakeConnection:
    def __init__(self) -> None:
        self._cursor = _FakeCursor()

    def __enter__(self) -> "_FakeConnection":
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None

    def cursor(self) -> _FakeCursor:
        return self._cursor


def test_ensure_schema_creates_token_usage_events_table_with_expected_columns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_conn = _FakeConnection()
    monkeypatch.setattr(schema.psycopg, "connect", lambda *a, **kw: fake_conn)

    schema.ensure_schema("postgresql://fake")

    executed_sql = "\n".join(q for q, _ in fake_conn._cursor.executed)
    assert "CREATE TABLE IF NOT EXISTS token_usage_events" in executed_sql
    assert "user_key TEXT NOT NULL" in executed_sql
    assert "thread_id TEXT" in executed_sql
    assert "provider TEXT NOT NULL" in executed_sql
    assert "model TEXT NOT NULL" in executed_sql
    assert "prompt_tokens INTEGER" in executed_sql
    assert "completion_tokens INTEGER" in executed_sql
    assert "total_tokens INTEGER" in executed_sql
    assert "source TEXT NOT NULL" in executed_sql
    assert "created_at TIMESTAMPTZ NOT NULL DEFAULT now()" in executed_sql


def test_ensure_schema_creates_indexes_on_user_key_created_at_and_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_conn = _FakeConnection()
    monkeypatch.setattr(schema.psycopg, "connect", lambda *a, **kw: fake_conn)

    schema.ensure_schema("postgresql://fake")

    executed_sql = "\n".join(q for q, _ in fake_conn._cursor.executed)
    assert "CREATE INDEX IF NOT EXISTS" in executed_sql
    assert "user_key" in executed_sql
    assert "created_at" in executed_sql
    assert "model" in executed_sql
    # Composite indexes required by design
    assert "ON token_usage_events (user_key, created_at" in executed_sql
    assert "ON token_usage_events (user_key, model)" in executed_sql


def test_ensure_schema_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_conn = _FakeConnection()
    monkeypatch.setattr(schema.psycopg, "connect", lambda *a, **kw: fake_conn)

    schema.ensure_schema("postgresql://fake")
    schema.ensure_schema("postgresql://fake")

    executed_count = len(fake_conn._cursor.executed)
    assert executed_count > 0
    assert executed_count % 2 == 0
