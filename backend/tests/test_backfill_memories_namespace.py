"""Testes de `scripts/backfill_memories_namespace.py`.

scoped-memory-namespace REQ-003 (user-data-isolation): após o backfill,
memórias legadas (`("memories",)`) só são recuperáveis em buscas feitas
pelo admin de bootstrap, nunca em buscas de outros usuários. Espelha o
estilo de `test_backfill_generated_files_ownership.py` (import direto do
script, fora de pacote; fake connection/cursor síncronos via
`_FakeCursor`/`_FakeConnection`).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import backfill_memories_namespace as backfill  # noqa: E402


class _FakeCursor:
    """Cursor fake que escreve em uma lista compartilhada de queries executadas.

    Cada `cursor()` na `_FakeConnection` retorna um NOVO `_FakeCursor`, mas
    todos compartilham a mesma `executed` da conexão (para que o teste
    consiga inspecionar todas as queries emitidas, mesmo após múltiplos
    `with conn.cursor() as cur:` em sequência — exatamente o que
    `run_backfill` faz: usa um cursor para ler admin/keys, outro para a
    transação).
    """

    def __init__(
        self,
        executed: list[tuple[str, tuple | None]],
        fetchone_queue: list[tuple | None],
        fetchall_queue: list[list[tuple]] | None = None,
    ) -> None:
        self._executed = executed
        self._fetchone_queue = fetchone_queue
        self._fetchall_queue = fetchall_queue or []

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

    def fetchall(self) -> list[tuple]:
        if self._fetchall_queue:
            return self._fetchall_queue.pop(0)
        return []


class _FakeConnection:
    def __init__(
        self,
        fetchone_queue: list[tuple | None] | None = None,
        fetchall_queue: list[list[tuple]] | None = None,
    ) -> None:
        self.executed: list[tuple[str, tuple | None]] = []
        # Cursores subsequentes compartilham as MESMAS filas para que o
        # `with conn.cursor() as cur:` seguinte não fique sem dados.
        self._fetchone_queue = list(fetchone_queue or [])
        self._fetchall_queue = list(fetchall_queue or [])
        self.rolled_back: bool = False
        self.committed: bool = False

    def __enter__(self) -> "_FakeConnection":
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None

    def cursor(self) -> _FakeCursor:
        return _FakeCursor(self.executed, self._fetchone_queue, self._fetchall_queue)

    def rollback(self) -> None:
        self.rolled_back = True

    def commit(self) -> None:
        self.committed = True


# --- list_legacy_keys ---------------------------------------------------


def test_list_legacy_keys_returns_all_keys_in_legacy_namespace() -> None:
    """A query lê `prefix = 'memories'` (o namespace legado de 1 segmento).

    Não usa `prefix LIKE 'memories.%'` porque isso pegaria namespaces
    aninhados (ex.: `("memories", "alice")` -> "memories.alice") — o
    namespace legado é exatamente `("memories",)`, 1 segmento, prefix
    igual a "memories".
    """
    conn = _FakeConnection(
        fetchall_queue=[[("mem-1",), ("mem-2",), ("mem-3",)]]
    )

    keys = backfill.list_legacy_keys(conn)

    assert keys == ["mem-1", "mem-2", "mem-3"]
    query, _ = conn.executed[0]
    assert "store" in query.lower()
    # Filtro exato, não prefixo
    assert "LIKE" not in query.upper() or "prefix = " in query.lower()


def test_list_legacy_keys_returns_empty_when_namespace_empty() -> None:
    conn = _FakeConnection(fetchall_queue=[[]])

    keys = backfill.list_legacy_keys(conn)

    assert keys == []


# --- resolve_admin_id ----------------------------------------------------


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


# --- run_backfill --------------------------------------------------------


def test_run_backfill_dry_run_does_not_write_or_delete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Em dry-run, lê chaves legadas e admin_id mas NÃO insere nem deleta nada."""
    conn = _FakeConnection(
        fetchone_queue=[("admin-id-1",)],
        fetchall_queue=[[("mem-1",), ("mem-2",)]],
    )
    monkeypatch.setattr(backfill.psycopg, "connect", lambda *a, **kw: conn)

    rows = backfill.run_backfill("postgresql://fake", dry_run=True)

    assert rows == [
        ("mem-1", "admin-id-1"),
        ("mem-2", "admin-id-1"),
    ]
    inserts = [q for q, _ in conn.executed if q.strip().upper().startswith("INSERT")]
    deletes = [q for q, _ in conn.executed if q.strip().upper().startswith("DELETE")]
    assert inserts == []
    assert deletes == []


def test_run_backfill_moves_each_key_to_admin_namespace_in_one_transaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Aplica: para cada chave legada, INSERT no novo namespace e DELETE do legado,
    dentro de uma única transação (`BEGIN`/`COMMIT`)."""
    conn = _FakeConnection(
        fetchone_queue=[
            ("admin-id-1",),  # resolve_admin_id
            ({"content": "fato"}, "2026-01-01", "2026-01-01"),  # _move_one para mem-1
            ({"content": "outro"}, "2026-01-02", "2026-01-02"),  # _move_one para mem-2
        ],
        fetchall_queue=[
            [("mem-1",), ("mem-2",)],  # list_legacy_keys
            [],  # store_vectors para mem-1 (sem embeddings)
            [],  # store_vectors para mem-2 (sem embeddings)
        ],
    )
    monkeypatch.setattr(backfill.psycopg, "connect", lambda *a, **kw: conn)

    rows = backfill.run_backfill("postgresql://fake", dry_run=False)

    assert rows == [
        ("mem-1", "admin-id-1"),
        ("mem-2", "admin-id-1"),
    ]
    queries = [q.strip().upper() for q, _ in conn.executed]
    # Transação explícita: BEGIN antes das escritas, COMMIT no final
    assert "BEGIN" in queries
    assert "COMMIT" in queries
    # E `conn.rollback()` NÃO foi chamado no caminho feliz
    assert conn.rolled_back is False
    # O script usa `cur.execute("COMMIT")` (psycopg3 fecha a transação SQL
    # ao receber o COMMIT do cursor), não `conn.commit()`.
    assert conn.committed is False
    # INSERTs no novo namespace (1 por chave)
    inserts = [(q, p) for q, p in conn.executed if q.strip().upper().startswith("INSERT")]
    assert len(inserts) == 2
    new_prefix = "memories.admin-id-1"
    seen_keys: set[str] = set()
    for query, params in inserts:
        assert "INSERT INTO store" in query
        assert params[0] == new_prefix
        seen_keys.add(params[1])
    assert seen_keys == {"mem-1", "mem-2"}
    # DELETEs do namespace legado (parametrizado, não literal `'memories'`)
    deletes = [(q, p) for q, p in conn.executed if q.strip().upper().startswith("DELETE")]
    assert len(deletes) == 2
    deleted_keys: set[str] = set()
    for query, params in deletes:
        assert "DELETE FROM store" in query
        # O primeiro parâmetro é o prefixo legado (`("memories",)` → "memories")
        assert params[0] == "memories"
        deleted_keys.add(params[1])
    assert deleted_keys == {"mem-1", "mem-2"}


def test_run_backfill_is_idempotent_when_legacy_namespace_already_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Segunda execução com namespace legado já vazio: nada a fazer, sem erro."""
    conn = _FakeConnection(
        fetchone_queue=[("admin-id-1",)],
        fetchall_queue=[[]],  # sem chaves legadas
    )
    monkeypatch.setattr(backfill.psycopg, "connect", lambda *a, **kw: conn)

    rows = backfill.run_backfill("postgresql://fake", dry_run=False)

    assert rows == []
    inserts = [q for q, _ in conn.executed if q.strip().upper().startswith("INSERT")]
    deletes = [q for q, _ in conn.executed if q.strip().upper().startswith("DELETE")]
    assert inserts == []
    assert deletes == []


def test_run_backfill_rolls_back_on_insert_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Se um INSERT falhar no meio, a transação é revertida (ROLLBACK) — o namespace
    legado não fica parcialmente migrado (REQ-003: estado consistente)."""

    class _RaisingConnection(_FakeConnection):
        def cursor(self) -> _FakeCursor:
            cur = super().cursor()
            # O segundo INSERT INTO store (do segundo item) falha — simulando
            # erro de constraint ou conflito. Mantém o estado do `executed`
            # antes de levantar para que o teste consiga inspecionar as
            # queries.
            original_execute = cur.execute
            insert_count = {"n": 0}

            def execute_with_eventual_failure(query, params=None):
                original_execute(query, params)
                if query.strip().upper().startswith("INSERT INTO STORE") and params is not None:
                    insert_count["n"] += 1
                    if insert_count["n"] == 2:
                        raise RuntimeError("simulated insert failure")

            cur.execute = execute_with_eventual_failure  # type: ignore[method-assign]
            return cur

    conn = _RaisingConnection(
        fetchone_queue=[
            ("admin-id-1",),  # resolve_admin_id
            ({"content": "fato"}, "2026-01-01", "2026-01-01"),  # _move_one mem-1 SELECT
            ({"content": "outro"}, "2026-01-02", "2026-01-02"),  # _move_one mem-2 SELECT
        ],
        fetchall_queue=[
            [("mem-1",), ("mem-2",)],  # list_legacy_keys
            [],  # store_vectors para mem-1
            [],  # store_vectors para mem-2
        ],
    )
    monkeypatch.setattr(backfill.psycopg, "connect", lambda *a, **kw: conn)

    with pytest.raises(RuntimeError, match="simulated insert failure"):
        backfill.run_backfill("postgresql://fake", dry_run=False)

    # Falhou no meio → a transação foi revertida via `conn.rollback()`,
    # não via `cur.execute("COMMIT")` (que abriria o commit).
    assert conn.rolled_back is True
    assert conn.committed is False
    # BEGIN foi emitido (a transação foi aberta), COMMIT não.
    queries = [q.strip().upper() for q, _ in conn.executed]
    assert "BEGIN" in queries
    assert "COMMIT" not in queries
