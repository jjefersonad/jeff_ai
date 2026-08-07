"""Testes de `src/infrastructure/persistence/scheduled_tasks_schema.py`.

Cobre a task `agendamento-jeff-cli-task-persistence-1`: DDL idempotente da
tabela `scheduled_tasks` (REQ-001 e REQ-008 do spec `task-scheduling`).
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from src.infrastructure.persistence import scheduled_tasks_schema as schema


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


def test_ensure_schema_creates_scheduled_tasks_table(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_conn = _FakeConnection()
    monkeypatch.setattr(schema.psycopg, "connect", lambda *a, **kw: fake_conn)

    schema.ensure_schema("postgresql://fake")

    executed_sql = "\n".join(fake_conn._cursor.executed)
    assert "CREATE TABLE IF NOT EXISTS scheduled_tasks" in executed_sql


@pytest.mark.parametrize(
    "column",
    [
        "prompt",
        "thread_id",
        "skills",
        "tool_scope",
        "schedule_kind",
        "schedule_expr",
        "status",
        "timeout_seconds",
        "last_run_at",
        "last_error",
        "owner_user_key",
        "delivery_user_key",
    ],
)
def test_ensure_schema_table_has_required_column(
    monkeypatch: pytest.MonkeyPatch, column: str
) -> None:
    fake_conn = _FakeConnection()
    monkeypatch.setattr(schema.psycopg, "connect", lambda *a, **kw: fake_conn)

    schema.ensure_schema("postgresql://fake")

    executed_sql = "\n".join(fake_conn._cursor.executed)
    assert column in executed_sql


def test_ensure_schema_status_check_includes_waiting_human(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """scheduled-channel-routines schema-1: CHECK de status inclui waiting_human."""
    fake_conn = _FakeConnection()
    monkeypatch.setattr(schema.psycopg, "connect", lambda *a, **kw: fake_conn)

    schema.ensure_schema("postgresql://fake")

    executed_sql = "\n".join(fake_conn._cursor.executed)
    assert "waiting_human" in executed_sql


def test_ensure_schema_adds_delivery_user_key_for_existing_tables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ALTER ADD COLUMN IF NOT EXISTS — bancos já provisionados sem a coluna."""
    fake_conn = _FakeConnection()
    monkeypatch.setattr(schema.psycopg, "connect", lambda *a, **kw: fake_conn)

    schema.ensure_schema("postgresql://fake")

    executed_sql = "\n".join(fake_conn._cursor.executed)
    assert "ADD COLUMN IF NOT EXISTS delivery_user_key" in executed_sql


def test_owner_user_key_column_is_not_null_without_fk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REQ-008: `owner_user_key` é TEXT NOT NULL — sem FK (cobre web e Telegram)."""
    fake_conn = _FakeConnection()
    monkeypatch.setattr(schema.psycopg, "connect", lambda *a, **kw: fake_conn)

    schema.ensure_schema("postgresql://fake")

    executed_sql = "\n".join(fake_conn._cursor.executed)
    owner_lines = [line for line in executed_sql.splitlines() if "owner_user_key" in line]
    assert owner_lines, "coluna owner_user_key não encontrada na DDL"
    for line in owner_lines:
        assert "REFERENCES" not in line
    assert any("NOT NULL" in line for line in owner_lines)


def test_ensure_schema_creates_owner_user_key_index(monkeypatch: pytest.MonkeyPatch) -> None:
    """Índice por owner_user_key para listagem eficiente por usuário (REQ-004/008)."""
    fake_conn = _FakeConnection()
    monkeypatch.setattr(schema.psycopg, "connect", lambda *a, **kw: fake_conn)

    schema.ensure_schema("postgresql://fake")

    executed_sql = "\n".join(fake_conn._cursor.executed)
    assert "CREATE INDEX IF NOT EXISTS" in executed_sql
    assert "owner_user_key" in executed_sql


def test_ensure_schema_runs_twice_without_raising(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_conn = _FakeConnection()
    monkeypatch.setattr(schema.psycopg, "connect", lambda *a, **kw: fake_conn)

    schema.ensure_schema("postgresql://fake")
    first_run = list(fake_conn._cursor.executed)
    schema.ensure_schema("postgresql://fake")
    second_run = fake_conn._cursor.executed[len(first_run) :]

    assert first_run == second_run


def test_schema_module_does_not_import_sqlalchemy() -> None:
    src = (
        Path(__file__).parent.parent
        / "src"
        / "infrastructure"
        / "persistence"
        / "scheduled_tasks_schema.py"
    ).read_text()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert "sqlalchemy" not in alias.name.lower()
        elif isinstance(node, ast.ImportFrom) and node.module:
            assert "sqlalchemy" not in node.module.lower()
