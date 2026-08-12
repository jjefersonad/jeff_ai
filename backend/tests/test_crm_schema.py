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
    "crm_leads",
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


def test_crm_leads_require_email_or_phone_or_company(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_conn = _FakeConnection()
    monkeypatch.setattr(schema.psycopg, "connect", lambda *a, **kw: fake_conn)

    schema.ensure_crm_schema("postgresql://fake")
    executed_sql = " ".join("\n".join(fake_conn._cursor.executed).split())
    assert (
        "email IS NOT NULL OR phone IS NOT NULL OR company_name IS NOT NULL"
        in executed_sql
    )


def test_ensure_crm_schema_adds_source_lead_id_columns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_conn = _FakeConnection()
    monkeypatch.setattr(schema.psycopg, "connect", lambda *a, **kw: fake_conn)

    schema.ensure_crm_schema("postgresql://fake")
    executed_sql = "\n".join(fake_conn._cursor.executed)

    assert (
        "ALTER TABLE crm_deals "
        "ADD COLUMN IF NOT EXISTS source_lead_id UUID REFERENCES crm_leads(id)"
        in executed_sql
    )
    assert (
        "ALTER TABLE crm_contacts "
        "ADD COLUMN IF NOT EXISTS source_lead_id UUID REFERENCES crm_leads(id)"
        in executed_sql
    )
    assert (
        "ALTER TABLE crm_companies "
        "ADD COLUMN IF NOT EXISTS source_lead_id UUID REFERENCES crm_leads(id)"
        in executed_sql
    )


def test_crm_deals_stage_check_rejects_lead_accepts_new_domain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_conn = _FakeConnection()
    monkeypatch.setattr(schema.psycopg, "connect", lambda *a, **kw: fake_conn)

    schema.ensure_crm_schema("postgresql://fake")
    executed_sql = " ".join("\n".join(fake_conn._cursor.executed).split())

    assert "crm_deals_stage_check" in executed_sql
    assert (
        "stage IN ('qualified', 'proposal', 'negotiation', 'won', 'lost')"
        in executed_sql
    )
    assert "DEFAULT 'qualified'" in executed_sql


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
