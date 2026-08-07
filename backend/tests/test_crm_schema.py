"""Testes de `src/infrastructure/persistence/crm_schema.py`.

Cobre `add-simple-crm-module-task-schema-1-unit-1`:
- WHEN `ensure_crm_schema(conninfo)` roda duas vezes
- THEN as quatro tabelas crm_* existem e a segunda chamada não levanta erro
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from src.infrastructure.persistence import crm_schema as schema


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


@pytest.mark.parametrize(
    "table",
    ["crm_companies", "crm_contacts", "crm_deals", "crm_notes"],
)
def test_ensure_crm_schema_creates_table(
    monkeypatch: pytest.MonkeyPatch, table: str
) -> None:
    fake_conn = _FakeConnection()
    monkeypatch.setattr(schema.psycopg, "connect", lambda *a, **kw: fake_conn)

    schema.ensure_crm_schema("postgresql://fake")

    executed_sql = "\n".join(fake_conn._cursor.executed)
    assert f"CREATE TABLE IF NOT EXISTS {table}" in executed_sql


def test_ensure_crm_schema_runs_twice_without_raising(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_conn = _FakeConnection()
    monkeypatch.setattr(schema.psycopg, "connect", lambda *a, **kw: fake_conn)

    schema.ensure_crm_schema("postgresql://fake")
    first_run = list(fake_conn._cursor.executed)
    schema.ensure_crm_schema("postgresql://fake")
    second_run = fake_conn._cursor.executed[len(first_run) :]

    assert first_run == second_run
    executed_sql = "\n".join(first_run)
    for table in ("crm_companies", "crm_contacts", "crm_deals", "crm_notes"):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in executed_sql


def test_crm_contacts_require_email_or_phone(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_conn = _FakeConnection()
    monkeypatch.setattr(schema.psycopg, "connect", lambda *a, **kw: fake_conn)

    schema.ensure_crm_schema("postgresql://fake")
    executed_sql = "\n".join(fake_conn._cursor.executed)
    assert "email IS NOT NULL OR phone IS NOT NULL" in executed_sql


def test_crm_notes_require_exactly_one_target(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_conn = _FakeConnection()
    monkeypatch.setattr(schema.psycopg, "connect", lambda *a, **kw: fake_conn)

    schema.ensure_crm_schema("postgresql://fake")
    executed_sql = " ".join("\n".join(fake_conn._cursor.executed).split())
    assert "contact_id IS NOT NULL" in executed_sql
    assert "company_id IS NOT NULL" in executed_sql
    assert "deal_id IS NOT NULL" in executed_sql
    # Exactly one target: sum of null-checks = 1
    assert (
        "(contact_id IS NOT NULL)::int + (company_id IS NOT NULL)::int + "
        "(deal_id IS NOT NULL)::int = 1"
    ) in executed_sql


def test_crm_schema_module_does_not_import_sqlalchemy() -> None:
    src = (
        Path(__file__).parent.parent
        / "src"
        / "infrastructure"
        / "persistence"
        / "crm_schema.py"
    ).read_text()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert "sqlalchemy" not in alias.name.lower()
        elif isinstance(node, ast.ImportFrom) and node.module:
            assert "sqlalchemy" not in node.module.lower()
