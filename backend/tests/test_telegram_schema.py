"""Testes de `src/infrastructure/telegram/schema.py` (tabela `telegram_threads`)."""
from __future__ import annotations

import pytest

from src.infrastructure.telegram import schema


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


def test_ensure_telegram_threads_schema_creates_table_with_expected_columns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_conn = _FakeConnection()
    monkeypatch.setattr(schema.psycopg, "connect", lambda *a, **kw: fake_conn)

    schema.ensure_telegram_threads_schema("postgresql://fake")

    executed_sql = "\n".join(q for q, _ in fake_conn._cursor.executed)
    assert "CREATE TABLE IF NOT EXISTS telegram_threads" in executed_sql
    assert "thread_id TEXT PRIMARY KEY" in executed_sql
    assert "chat_id TEXT NOT NULL" in executed_sql
    assert "created_at TIMESTAMPTZ NOT NULL DEFAULT now()" in executed_sql


def test_ensure_telegram_threads_schema_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_conn = _FakeConnection()
    monkeypatch.setattr(schema.psycopg, "connect", lambda *a, **kw: fake_conn)

    schema.ensure_telegram_threads_schema("postgresql://fake")
    schema.ensure_telegram_threads_schema("postgresql://fake")

    executed_count = len(fake_conn._cursor.executed)
    assert executed_count > 0
    assert executed_count % 2 == 0


def test_ensure_telegram_threads_schema_adds_title_and_active_columns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_conn = _FakeConnection()
    monkeypatch.setattr(schema.psycopg, "connect", lambda *a, **kw: fake_conn)

    schema.ensure_telegram_threads_schema("postgresql://fake")

    executed_sql = "\n".join(q for q, _ in fake_conn._cursor.executed)
    assert "ALTER TABLE telegram_threads ADD COLUMN IF NOT EXISTS title TEXT" in executed_sql
    assert (
        "ALTER TABLE telegram_threads ADD COLUMN IF NOT EXISTS active BOOLEAN NOT NULL DEFAULT FALSE"
        in executed_sql
    )


def test_ensure_telegram_threads_schema_creates_unique_partial_active_index(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_conn = _FakeConnection()
    monkeypatch.setattr(schema.psycopg, "connect", lambda *a, **kw: fake_conn)

    schema.ensure_telegram_threads_schema("postgresql://fake")

    executed_sql = "\n".join(q for q, _ in fake_conn._cursor.executed)
    assert "CREATE UNIQUE INDEX IF NOT EXISTS telegram_threads_one_active_per_chat" in executed_sql
    assert "ON telegram_threads(chat_id) WHERE active" in executed_sql


def test_ensure_telegram_threads_schema_called_twice_does_not_raise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_conn = _FakeConnection()
    monkeypatch.setattr(schema.psycopg, "connect", lambda *a, **kw: fake_conn)

    schema.ensure_telegram_threads_schema("postgresql://fake")
    schema.ensure_telegram_threads_schema("postgresql://fake")


# ---------------------------------------------------------------------------
# thread_id as PRIMARY KEY (telegram-slash-commands: multiple threads per
# chat_id require chat_id to stop being the sole PK).
# ---------------------------------------------------------------------------


def test_ensure_telegram_threads_schema_creates_table_with_thread_id_primary_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_conn = _FakeConnection()
    monkeypatch.setattr(schema.psycopg, "connect", lambda *a, **kw: fake_conn)

    schema.ensure_telegram_threads_schema("postgresql://fake")

    executed_sql = "\n".join(q for q, _ in fake_conn._cursor.executed)
    assert "CREATE TABLE IF NOT EXISTS telegram_threads" in executed_sql
    assert "thread_id TEXT PRIMARY KEY" in executed_sql
    assert "chat_id TEXT NOT NULL" in executed_sql
    assert "chat_id TEXT PRIMARY KEY" not in executed_sql


def test_ensure_telegram_threads_schema_migrates_chat_id_primary_key_to_thread_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_conn = _FakeConnection()
    monkeypatch.setattr(schema.psycopg, "connect", lambda *a, **kw: fake_conn)

    schema.ensure_telegram_threads_schema("postgresql://fake")

    executed_sql = "\n".join(q for q, _ in fake_conn._cursor.executed)
    assert "constraint_type = 'PRIMARY KEY'" in executed_sql
    assert "kcu.column_name = 'chat_id'" in executed_sql
    assert "ADD PRIMARY KEY (thread_id)" in executed_sql


def test_ensure_telegram_threads_schema_creates_chat_id_index(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_conn = _FakeConnection()
    monkeypatch.setattr(schema.psycopg, "connect", lambda *a, **kw: fake_conn)

    schema.ensure_telegram_threads_schema("postgresql://fake")

    executed_sql = "\n".join(q for q, _ in fake_conn._cursor.executed)
    assert "CREATE INDEX IF NOT EXISTS telegram_threads_chat_id_idx" in executed_sql
    assert "ON telegram_threads(chat_id)" in executed_sql
