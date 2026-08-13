"""Testes de `src/infrastructure/persistence/crm_schema.py`.

Cobre schema v1 + extensão location/custom fields/field_definitions:
- WHEN `ensure_crm_schema(conninfo)` roda duas vezes
- THEN as tabelas crm_* (incl. field_definitions) existem e a 2ª chamada é idempotente
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from src.infrastructure.persistence import crm_schema as schema

_CRM_TABLES = (
    "crm_companies",
    "crm_contacts",
    "crm_deals",
    "crm_notes",
    "crm_field_definitions",
)


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


@pytest.mark.parametrize("table", list(_CRM_TABLES))
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
    for table in _CRM_TABLES:
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


def test_ensure_crm_schema_adds_location_and_custom_values_columns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_conn = _FakeConnection()
    monkeypatch.setattr(schema.psycopg, "connect", lambda *a, **kw: fake_conn)

    schema.ensure_crm_schema("postgresql://fake")
    executed_sql = "\n".join(fake_conn._cursor.executed)

    assert "ALTER TABLE crm_contacts ADD COLUMN IF NOT EXISTS city TEXT" in executed_sql
    assert "ALTER TABLE crm_contacts ADD COLUMN IF NOT EXISTS state TEXT" in executed_sql
    assert "ALTER TABLE crm_companies ADD COLUMN IF NOT EXISTS city TEXT" in executed_sql
    assert "ALTER TABLE crm_companies ADD COLUMN IF NOT EXISTS state TEXT" in executed_sql
    assert "custom_values JSONB" in executed_sql
    assert (
        "ALTER TABLE crm_notes ADD COLUMN IF NOT EXISTS archived_at TIMESTAMPTZ"
        in executed_sql
    )


def test_crm_deals_stage_check_includes_lead(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_conn = _FakeConnection()
    monkeypatch.setattr(schema.psycopg, "connect", lambda *a, **kw: fake_conn)

    schema.ensure_crm_schema("postgresql://fake")
    executed_sql = " ".join("\n".join(fake_conn._cursor.executed).split())

    assert "crm_deals_stage_check" in executed_sql
    assert "'lead'" in executed_sql
    assert "'qualified'" in executed_sql
    assert "'negotiation'" in executed_sql
    assert "DEFAULT 'lead'" in executed_sql


def test_ensure_crm_schema_drops_crm_leads_table(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """unit-1: DROP TABLE crm_leads; never CREATE TABLE crm_leads."""
    fake_conn = _FakeConnection()
    monkeypatch.setattr(schema.psycopg, "connect", lambda *a, **kw: fake_conn)

    schema.ensure_crm_schema("postgresql://fake")
    executed_sql = "\n".join(fake_conn._cursor.executed)
    assert "DROP TABLE IF EXISTS crm_leads" in executed_sql
    assert "CREATE TABLE IF NOT EXISTS crm_leads" not in executed_sql


def test_ensure_crm_schema_drops_source_lead_id_on_all_entities(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """unit-2: DROP COLUMN source_lead_id on deals, contacts, companies."""
    fake_conn = _FakeConnection()
    monkeypatch.setattr(schema.psycopg, "connect", lambda *a, **kw: fake_conn)

    schema.ensure_crm_schema("postgresql://fake")
    executed_sql = "\n".join(fake_conn._cursor.executed)
    assert "ALTER TABLE crm_deals DROP COLUMN IF EXISTS source_lead_id" in executed_sql
    assert (
        "ALTER TABLE crm_contacts DROP COLUMN IF EXISTS source_lead_id" in executed_sql
    )
    assert (
        "ALTER TABLE crm_companies DROP COLUMN IF EXISTS source_lead_id" in executed_sql
    )


def test_ensure_crm_schema_drop_leads_is_idempotent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """unit-3: second ensure_crm_schema run still emits DROP IF EXISTS."""
    fake_conn = _FakeConnection()
    monkeypatch.setattr(schema.psycopg, "connect", lambda *a, **kw: fake_conn)

    schema.ensure_crm_schema("postgresql://fake")
    first_run = list(fake_conn._cursor.executed)
    schema.ensure_crm_schema("postgresql://fake")
    second_run = fake_conn._cursor.executed[len(first_run) :]

    second_sql = "\n".join(second_run)
    assert "DROP TABLE IF EXISTS crm_leads" in second_sql
    assert "ALTER TABLE crm_deals DROP COLUMN IF EXISTS source_lead_id" in second_sql
    assert (
        "ALTER TABLE crm_contacts DROP COLUMN IF EXISTS source_lead_id" in second_sql
    )
    assert (
        "ALTER TABLE crm_companies DROP COLUMN IF EXISTS source_lead_id" in second_sql
    )


def test_crm_field_definitions_unique_user_entity_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_conn = _FakeConnection()
    monkeypatch.setattr(schema.psycopg, "connect", lambda *a, **kw: fake_conn)

    schema.ensure_crm_schema("postgresql://fake")
    executed_sql = "\n".join(fake_conn._cursor.executed)
    assert "UNIQUE (user_id, entity, key)" in executed_sql
    assert "entity IN ('contact', 'company', 'deal')" in executed_sql
    assert "field_type IN ('text', 'number', 'boolean')" in executed_sql


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
