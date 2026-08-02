"""Testes de `scripts/backfill_mcp_servers_ownership.py`.

scoped-mcp-config REQ-002 (task `user-data-isolation-task-backfill-3`):
servidores MCP configurados antes do change `user-data-isolation` (schema
global) ficam associados ao admin de bootstrap após a migração. Espelha o
estilo de `test_backfill_generated_files_ownership.py` (import direto do
script, fora de pacote; fake connection/cursor síncronos para
`resolve_admin_id`, já que este script não grava nada em Postgres — só
lê/escreve o JSON).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import backfill_mcp_servers_ownership as backfill  # noqa: E402


class _FakeCursor:
    def __init__(self, executed: list[tuple[str, tuple | None]], fetchone_queue: list[tuple | None]) -> None:
        self._executed = executed
        self._fetchone_queue = fetchone_queue

    def __enter__(self) -> "_FakeCursor":
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None

    def execute(self, query: str, params: tuple | None = None) -> None:
        self._executed.append((query, params))

    def fetchone(self) -> tuple | None:
        if self._fetchone_queue:
            return self._fetchone_queue.pop(0)
        return None


class _FakeConnection:
    def __init__(self, fetchone_queue: list[tuple | None]) -> None:
        self.executed: list[tuple[str, tuple | None]] = []
        self._fetchone_queue = list(fetchone_queue)

    def __enter__(self) -> "_FakeConnection":
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None

    def cursor(self) -> _FakeCursor:
        return _FakeCursor(self.executed, self._fetchone_queue)


def _write_config(path: Path, raw: dict) -> None:
    path.write_text(json.dumps(raw), encoding="utf-8")


# --- schema detection (_is_server_entry / collect_legacy_servers) --------


def test_collect_legacy_servers_detects_stdio_entries() -> None:
    raw = {"mcpServers": {"srv": {"command": "npx", "args": []}}}
    assert backfill.collect_legacy_servers(raw) == {"srv": {"command": "npx", "args": []}}


def test_collect_legacy_servers_detects_http_entries() -> None:
    raw = {"mcpServers": {"srv": {"transport": "http", "url": "https://x/mcp"}}}
    assert backfill.collect_legacy_servers(raw) == {
        "srv": {"transport": "http", "url": "https://x/mcp"}
    }


def test_collect_legacy_servers_ignores_partitioned_entries() -> None:
    raw = {"mcpServers": {"user-a": {"srv": {"command": "npx"}}}}
    assert backfill.collect_legacy_servers(raw) == {}


def test_collect_legacy_servers_empty_on_missing_key() -> None:
    assert backfill.collect_legacy_servers({}) == {}


# --- resolve_admin_id -----------------------------------------------------


def test_resolve_admin_id_returns_first_admin() -> None:
    conn = _FakeConnection(fetchone_queue=[("admin-id-1",)])

    result = backfill.resolve_admin_id(conn)

    assert result == "admin-id-1"
    query, _ = conn.executed[0]
    assert "role = 'admin'" in query


def test_resolve_admin_id_raises_when_no_admin_exists() -> None:
    conn = _FakeConnection(fetchone_queue=[None])

    with pytest.raises(backfill.BackfillError):
        backfill.resolve_admin_id(conn)


# --- run_backfill -----------------------------------------------------


def test_run_backfill_on_missing_file_is_noop(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    conn = _FakeConnection(fetchone_queue=[])
    monkeypatch.setattr(backfill.psycopg, "connect", lambda *a, **kw: conn)

    moved, skipped = backfill.run_backfill(
        tmp_path / "missing.json", "postgresql://fake", dry_run=False
    )

    assert (moved, skipped) == ([], [])
    assert conn.executed == []  # não conecta ao Postgres sem nada a migrar


def test_run_backfill_dry_run_does_not_write_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "mcp_servers.json"
    _write_config(path, {"mcpServers": {"srv": {"command": "npx"}}})
    conn = _FakeConnection(fetchone_queue=[("admin-id-1",)])
    monkeypatch.setattr(backfill.psycopg, "connect", lambda *a, **kw: conn)

    moved, skipped = backfill.run_backfill(path, "postgresql://fake", dry_run=True)

    assert moved == [("srv", "admin-id-1")]
    assert skipped == []
    # dry-run nunca grava — arquivo permanece no formato global antigo.
    assert json.loads(path.read_text()) == {"mcpServers": {"srv": {"command": "npx"}}}


def test_run_backfill_moves_legacy_server_under_admin_partition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "mcp_servers.json"
    _write_config(path, {"mcpServers": {"srv": {"command": "npx", "args": ["-y"]}}})
    conn = _FakeConnection(fetchone_queue=[("admin-id-1",)])
    monkeypatch.setattr(backfill.psycopg, "connect", lambda *a, **kw: conn)

    moved, skipped = backfill.run_backfill(path, "postgresql://fake", dry_run=False)

    assert moved == [("srv", "admin-id-1")]
    assert skipped == []
    raw = json.loads(path.read_text())
    assert raw["mcpServers"] == {"admin-id-1": {"srv": {"command": "npx", "args": ["-y"]}}}


def test_run_backfill_skips_on_name_collision_preserving_admin_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "mcp_servers.json"
    _write_config(
        path,
        {
            "mcpServers": {
                "srv": {"command": "legacy-cmd"},
                "admin-id-1": {"srv": {"command": "admins-own-cmd"}},
            }
        },
    )
    conn = _FakeConnection(fetchone_queue=[("admin-id-1",)])
    monkeypatch.setattr(backfill.psycopg, "connect", lambda *a, **kw: conn)

    moved, skipped = backfill.run_backfill(path, "postgresql://fake", dry_run=False)

    assert moved == []
    assert skipped == [("srv", "admin-id-1")]
    raw = json.loads(path.read_text())
    # versão do admin preservada; entrada legada removida do nível raiz.
    assert raw["mcpServers"] == {"admin-id-1": {"srv": {"command": "admins-own-cmd"}}}


def test_run_backfill_is_idempotent_on_second_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "mcp_servers.json"
    _write_config(path, {"mcpServers": {"srv": {"command": "npx"}}})
    conn = _FakeConnection(fetchone_queue=[("admin-id-1",)])
    monkeypatch.setattr(backfill.psycopg, "connect", lambda *a, **kw: conn)

    backfill.run_backfill(path, "postgresql://fake", dry_run=False)

    # segunda execução: arquivo já 100% particionado — nenhuma entrada legada,
    # não conecta de novo ao Postgres, não reescreve o arquivo.
    before = path.read_text()
    moved, skipped = backfill.run_backfill(path, "postgresql://fake", dry_run=False)

    assert (moved, skipped) == ([], [])
    assert path.read_text() == before
