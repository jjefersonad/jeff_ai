"""Testes de `ensure_agent_profiles_schema` (schema-1 / REQ-004)."""
from __future__ import annotations

import pytest

from src.infrastructure.persistence import agent_profiles_schema as schema


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

    def commit(self) -> None:
        return None


def test_ensure_schema_creates_mcp_allowlist_column(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_conn = _FakeConnection()
    monkeypatch.setattr(schema.psycopg, "connect", lambda *a, **kw: fake_conn)

    schema.ensure_agent_profiles_schema("postgresql://fake")

    executed_sql = "\n".join(fake_conn._cursor.executed)
    assert "CREATE TABLE IF NOT EXISTS agent_profiles" in executed_sql
    assert "mcp_allowlist JSONB" in executed_sql
    assert (
        "ALTER TABLE agent_profiles ADD COLUMN IF NOT EXISTS mcp_allowlist JSONB"
        in executed_sql
    )
