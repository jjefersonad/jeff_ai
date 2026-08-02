"""Testes de `src/infrastructure/persistence/user_integrations_schema.py`.

Cobre a task `user-integration-credentials-task-db-1`: DDL idempotente da
tabela `user_integrations` (REQ-002/REQ-003 do spec
`user-integration-credentials-store`).
"""
from __future__ import annotations

import pytest

from src.infrastructure.persistence import user_integrations_schema as schema


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


def test_ensure_schema_creates_user_integrations_table(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_conn = _FakeConnection()
    monkeypatch.setattr(schema.psycopg, "connect", lambda *a, **kw: fake_conn)

    schema.ensure_schema("postgresql://fake")

    executed_sql = "\n".join(fake_conn._cursor.executed)
    assert "CREATE TABLE IF NOT EXISTS user_integrations" in executed_sql


@pytest.mark.parametrize(
    "column",
    ["id", "user_id", "integration_type", "config", "created_at", "updated_at"],
)
def test_ensure_schema_table_has_required_column(
    monkeypatch: pytest.MonkeyPatch, column: str
) -> None:
    fake_conn = _FakeConnection()
    monkeypatch.setattr(schema.psycopg, "connect", lambda *a, **kw: fake_conn)

    schema.ensure_schema("postgresql://fake")

    executed_sql = "\n".join(fake_conn._cursor.executed)
    assert column in executed_sql


def test_config_column_is_jsonb_with_no_plaintext_only_constraint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REQ-002: `config` precisa comportar ciphertext — JSONB, sem CHECK que restrinja o formato."""
    fake_conn = _FakeConnection()
    monkeypatch.setattr(schema.psycopg, "connect", lambda *a, **kw: fake_conn)

    schema.ensure_schema("postgresql://fake")

    executed_sql = "\n".join(fake_conn._cursor.executed)
    config_lines = [line for line in executed_sql.splitlines() if "config" in line]
    assert config_lines, "coluna config não encontrada na DDL"
    assert any("JSONB" in line for line in config_lines)
    assert not any("CHECK" in line for line in config_lines)


def test_user_id_column_is_fk_to_users(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_conn = _FakeConnection()
    monkeypatch.setattr(schema.psycopg, "connect", lambda *a, **kw: fake_conn)

    schema.ensure_schema("postgresql://fake")

    executed_sql = "\n".join(fake_conn._cursor.executed)
    assert "REFERENCES users(id)" in executed_sql


def test_ensure_schema_called_twice_does_not_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_conn = _FakeConnection()
    monkeypatch.setattr(schema.psycopg, "connect", lambda *a, **kw: fake_conn)

    schema.ensure_schema("postgresql://fake")
    schema.ensure_schema("postgresql://fake")


def test_ensure_schema_runs_twice_with_identical_statements(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_conn = _FakeConnection()
    monkeypatch.setattr(schema.psycopg, "connect", lambda *a, **kw: fake_conn)

    schema.ensure_schema("postgresql://fake")
    first_run = list(fake_conn._cursor.executed)
    schema.ensure_schema("postgresql://fake")
    second_run = fake_conn._cursor.executed[len(first_run) :]

    assert first_run == second_run
