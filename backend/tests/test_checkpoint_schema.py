"""Testes de `src/infrastructure/agent_runtime/checkpoint_schema.py`."""
from __future__ import annotations

import pytest

from src.infrastructure.agent_runtime import checkpoint_schema as schema


class _SchemaState:
    def __init__(self) -> None:
        # UUID-shaped legacy schema from LangGraph API — no task_path yet.
        self.columns: dict[str, dict[str, str]] = {
            "checkpoint_writes": {
                "thread_id": "uuid",
                "checkpoint_ns": "text",
                "checkpoint_id": "uuid",
                "task_id": "uuid",
                "idx": "int4",
                "channel": "text",
                "type": "text",
                "blob": "bytea",
            }
        }
        self.row_marker = "seed-row"

    def has_column(self, table: str, column: str) -> bool:
        return column in self.columns.get(table, {})

    def add_column(self, table: str, column: str, udt: str) -> None:
        self.columns.setdefault(table, {})[column] = udt


class _FakeCursor:
    def __init__(self, state: _SchemaState) -> None:
        self._state = state
        self.executed: list[tuple[str, tuple | None]] = []
        self._last_fetch: list[tuple] = []

    def __enter__(self) -> "_FakeCursor":
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None

    def execute(self, query: str, params: tuple | None = None) -> None:
        self.executed.append((query, params))
        normalized = " ".join(query.split()).lower()
        self._last_fetch = []

        if "information_schema.columns" in normalized:
            cols = self._state.columns.get("checkpoint_writes", {})
            if params is None:
                self._last_fetch = [(name, udt) for name, udt in cols.items()]
                return
            if len(params) == 2 and params[1] == "task_path":
                # SELECT ... WHERE table_name = %s AND column_name = %s
                if self._state.has_column("checkpoint_writes", "task_path"):
                    self._last_fetch = [("task_path", "text")]
                return
            if len(params) == 1 and isinstance(params[0], (list, tuple)):
                wanted = set(params[0])
                self._last_fetch = [
                    (name, udt) for name, udt in cols.items() if name in wanted
                ]
                return
            return

        if (
            "alter table checkpoint_writes add column if not exists task_path"
            in normalized
        ):
            self._state.add_column("checkpoint_writes", "task_path", "text")

    def fetchone(self) -> tuple | None:
        if not self._last_fetch:
            return None
        return self._last_fetch[0]

    def fetchall(self) -> list[tuple]:
        return list(self._last_fetch)


class _FakeConnection:
    def __init__(self, state: _SchemaState) -> None:
        self._state = state
        self._cursor = _FakeCursor(state)

    def __enter__(self) -> "_FakeConnection":
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None

    def cursor(self) -> _FakeCursor:
        return self._cursor


def _patch_connect(
    monkeypatch: pytest.MonkeyPatch, state: _SchemaState
) -> _FakeConnection:
    fake_conn = _FakeConnection(state)
    monkeypatch.setattr(schema.psycopg, "connect", lambda *a, **kw: fake_conn)
    return fake_conn


def _column_exists(conninfo: str, table: str, column: str) -> bool:
    """Mirror information_schema checks after ensure (uses patched connect)."""
    with schema.psycopg.connect(conninfo, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_name = %s AND column_name = %s
                """,
                (table, column),
            )
            return cur.fetchone() is not None


def _column_udt(conninfo: str, column: str) -> str | None:
    with schema.psycopg.connect(conninfo, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT column_name, udt_name
                FROM information_schema.columns
                WHERE table_name = 'checkpoint_writes'
                  AND column_name = ANY(%s)
                """,
                ([column],),
            )
            row = cur.fetchone()
            return None if row is None else str(row[1])


def test_ensure_missing_task_path_creates_column_visible_in_information_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _SchemaState()
    assert not state.has_column("checkpoint_writes", "task_path")
    fake_conn = _patch_connect(monkeypatch, state)

    schema.ensure_langgraph_checkpoint_schema("postgresql://fake")

    assert _column_exists("postgresql://fake", "checkpoint_writes", "task_path")
    executed_sql = "\n".join(q for q, _ in fake_conn._cursor.executed)
    assert (
        "ALTER TABLE checkpoint_writes ADD COLUMN IF NOT EXISTS task_path "
        "TEXT NOT NULL DEFAULT ''" in executed_sql
    )


def test_ensure_is_idempotent_when_task_path_already_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _SchemaState()
    state.add_column("checkpoint_writes", "task_path", "text")
    marker_before = state.row_marker
    _patch_connect(monkeypatch, state)

    schema.ensure_langgraph_checkpoint_schema("postgresql://fake")
    schema.ensure_langgraph_checkpoint_schema("postgresql://fake")

    assert state.has_column("checkpoint_writes", "task_path")
    assert state.row_marker == marker_before


def test_ensure_preserves_uuid_column_types(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _SchemaState()
    fake_conn = _patch_connect(monkeypatch, state)

    schema.ensure_langgraph_checkpoint_schema("postgresql://fake")

    executed_sql = "\n".join(q for q, _ in fake_conn._cursor.executed).lower()
    assert "create table" not in executed_sql
    assert "drop table" not in executed_sql
    assert _column_udt("postgresql://fake", "thread_id") == "uuid"
    assert _column_udt("postgresql://fake", "checkpoint_id") == "uuid"
    assert _column_udt("postgresql://fake", "task_id") == "uuid"
