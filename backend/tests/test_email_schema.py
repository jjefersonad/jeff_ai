"""Testes de `src/infrastructure/persistence/email_schema.py`.

Cobre `email-client-imap-mvp-task-schema-2` (REQ-001..005 email-account-management,
REQ-001..006 email-inbox):
- WHEN `ensure_email_schema(conninfo)` roda
- THEN as tabelas `email_accounts`/`emails`/`email_attachments` existem
- WHEN roda duas vezes
- THEN a 2ª chamada é idempotente (mesmo SQL executado)
"""
from __future__ import annotations

import pytest

from src.infrastructure.persistence import email_schema as schema

_EMAIL_TABLES = ("email_accounts", "emails", "email_attachments")


class _FakeCursor:
    def __init__(self) -> None:
        self.executed: list[str] = []

    def __enter__(self) -> "_FakeCursor":
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None

    def execute(self, query: str) -> None:
        self.executed.append(query)


class _FakeConnection:
    def __init__(self) -> None:
        self._cursor = _FakeCursor()

    def __enter__(self) -> "_FakeConnection":
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None

    def cursor(self) -> _FakeCursor:
        return self._cursor


@pytest.mark.parametrize("table", list(_EMAIL_TABLES))
def test_ensure_email_schema_creates_table(
    monkeypatch: pytest.MonkeyPatch, table: str
) -> None:
    fake_conn = _FakeConnection()
    monkeypatch.setattr(schema.psycopg, "connect", lambda *a, **kw: fake_conn)

    schema.ensure_email_schema("postgresql://fake")

    executed_sql = "\n".join(fake_conn._cursor.executed)
    assert f"CREATE TABLE IF NOT EXISTS {table}" in executed_sql


def test_ensure_email_schema_runs_twice_without_raising(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_conn = _FakeConnection()
    monkeypatch.setattr(schema.psycopg, "connect", lambda *a, **kw: fake_conn)

    schema.ensure_email_schema("postgresql://fake")
    first_run = list(fake_conn._cursor.executed)
    schema.ensure_email_schema("postgresql://fake")
    second_run = fake_conn._cursor.executed[len(first_run) :]

    assert first_run == second_run
    executed_sql = "\n".join(first_run)
    for table in _EMAIL_TABLES:
        assert f"CREATE TABLE IF NOT EXISTS {table}" in executed_sql


def test_emails_unique_account_message_id(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_conn = _FakeConnection()
    monkeypatch.setattr(schema.psycopg, "connect", lambda *a, **kw: fake_conn)

    schema.ensure_email_schema("postgresql://fake")
    executed_sql = " ".join("\n".join(fake_conn._cursor.executed).split())
    assert "UNIQUE (email_account_id, message_id)" in executed_sql


def test_email_accounts_status_check(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_conn = _FakeConnection()
    monkeypatch.setattr(schema.psycopg, "connect", lambda *a, **kw: fake_conn)

    schema.ensure_email_schema("postgresql://fake")
    executed_sql = "\n".join(fake_conn._cursor.executed)
    assert "status IN ('connected', 'error', 'syncing')" in executed_sql
