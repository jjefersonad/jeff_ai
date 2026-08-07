"""Testes de `src/infrastructure/whatsapp/schema.py` (tabela `whatsapp_threads`)."""
from __future__ import annotations

import pytest

from src.infrastructure.whatsapp import schema


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


def test_ensure_whatsapp_threads_schema_adds_title_and_active_columns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_conn = _FakeConnection()
    monkeypatch.setattr(schema.psycopg, "connect", lambda *a, **kw: fake_conn)

    schema.ensure_whatsapp_threads_schema("postgresql://fake")

    executed_sql = "\n".join(q for q, _ in fake_conn._cursor.executed)
    assert "ALTER TABLE whatsapp_threads ADD COLUMN IF NOT EXISTS title TEXT" in executed_sql
    assert (
        "ALTER TABLE whatsapp_threads ADD COLUMN IF NOT EXISTS active BOOLEAN NOT NULL DEFAULT FALSE"
        in executed_sql
    )


def test_ensure_whatsapp_threads_schema_creates_unique_partial_active_index(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_conn = _FakeConnection()
    monkeypatch.setattr(schema.psycopg, "connect", lambda *a, **kw: fake_conn)

    schema.ensure_whatsapp_threads_schema("postgresql://fake")

    executed_sql = "\n".join(q for q, _ in fake_conn._cursor.executed)
    assert (
        "CREATE UNIQUE INDEX IF NOT EXISTS whatsapp_threads_one_active_per_number" in executed_sql
    )
    assert "ON whatsapp_threads(phone_number) WHERE active" in executed_sql


def test_ensure_whatsapp_threads_schema_migrates_phone_number_primary_key_and_activates_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REQ-008: linha pré-existente (PK antiga `phone_number`) migra para `thread_id` como PK
    e é marcada `active=TRUE` — diferente do Telegram, que deixa `active=FALSE` até o usuário
    mandar um comando (ver design, Decision "whatsapp_threads migra de phone_number PK...")."""
    fake_conn = _FakeConnection()
    monkeypatch.setattr(schema.psycopg, "connect", lambda *a, **kw: fake_conn)

    schema.ensure_whatsapp_threads_schema("postgresql://fake")

    executed_sql = "\n".join(q for q, _ in fake_conn._cursor.executed)
    assert "constraint_type = 'PRIMARY KEY'" in executed_sql
    assert "kcu.column_name = 'phone_number'" in executed_sql
    assert "ADD PRIMARY KEY (thread_id)" in executed_sql
    assert "UPDATE whatsapp_threads SET active = TRUE" in executed_sql


def test_ensure_whatsapp_threads_schema_creates_phone_number_index(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_conn = _FakeConnection()
    monkeypatch.setattr(schema.psycopg, "connect", lambda *a, **kw: fake_conn)

    schema.ensure_whatsapp_threads_schema("postgresql://fake")

    executed_sql = "\n".join(q for q, _ in fake_conn._cursor.executed)
    assert "CREATE INDEX IF NOT EXISTS whatsapp_threads_phone_number_idx" in executed_sql
    assert "ON whatsapp_threads(phone_number)" in executed_sql


def test_ensure_whatsapp_threads_schema_called_twice_does_not_raise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_conn = _FakeConnection()
    monkeypatch.setattr(schema.psycopg, "connect", lambda *a, **kw: fake_conn)

    schema.ensure_whatsapp_threads_schema("postgresql://fake")
    schema.ensure_whatsapp_threads_schema("postgresql://fake")
