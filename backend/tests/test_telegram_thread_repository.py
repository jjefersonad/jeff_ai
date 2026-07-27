"""Testes de `src/infrastructure/telegram/thread_repository.py` (get_or_create_thread_id)."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from src.infrastructure.telegram import thread_repository

# ============================================================================
# Transactional fake table for get_or_create_thread_id / set_active_thread /
# create_thread_for_chat — these run multi-statement transactions over the
# "active" invariant (thread_id is the PK; chat_id may repeat across rows,
# see the schema migration in test_telegram_schema.py).
# ============================================================================


class _TxCursor:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows
        self._last_result: object = None
        self.rowcount = 0

    def __enter__(self) -> "_TxCursor":
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None

    def execute(self, query: str, params: tuple) -> None:
        q = query.strip()
        if q.startswith("SELECT thread_id FROM telegram_threads") and "active = TRUE" in q:
            (chat_id,) = params
            match = next(
                (r for r in self._rows if r["chat_id"] == chat_id and r["active"]), None
            )
            self._last_result = (match["thread_id"],) if match is not None else None
        elif q.startswith("SELECT 1 FROM telegram_threads") and "thread_id = %s" in q:
            chat_id, thread_id = params
            exists = any(
                r["chat_id"] == chat_id and r["thread_id"] == thread_id for r in self._rows
            )
            self._last_result = (1,) if exists else None
        elif q.startswith("SELECT 1 FROM telegram_threads") and "title = %s" in q:
            chat_id, title = params
            exists = any(r["chat_id"] == chat_id and r["title"] == title for r in self._rows)
            self._last_result = (1,) if exists else None
        elif q.startswith("UPDATE telegram_threads SET active = FALSE") and "!=" in q:
            chat_id, exclude_thread_id = params
            for r in self._rows:
                if r["chat_id"] == chat_id and r["active"] and r["thread_id"] != exclude_thread_id:
                    r["active"] = False
        elif q.startswith("UPDATE telegram_threads SET active = FALSE"):
            (chat_id,) = params
            for r in self._rows:
                if r["chat_id"] == chat_id and r["active"]:
                    r["active"] = False
        elif q.startswith("UPDATE telegram_threads SET active = TRUE"):
            chat_id, thread_id = params
            target = next(
                (r for r in self._rows if r["chat_id"] == chat_id and r["thread_id"] == thread_id),
                None,
            )
            if target is not None:
                target["active"] = True
                self.rowcount = 1
            else:
                self.rowcount = 0
        elif q.startswith("INSERT INTO telegram_threads"):
            chat_id, thread_id, title = params
            self._rows.append(
                {
                    "chat_id": chat_id,
                    "thread_id": thread_id,
                    "title": title,
                    "active": True,
                    "created_at": datetime.now(UTC),
                }
            )
        else:
            raise AssertionError(f"Query inesperada no fake cursor transacional: {query!r}")

    def fetchone(self) -> object:
        return self._last_result


class _TxConnection:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._cursor = _TxCursor(rows)
        self.committed = False
        self.rolled_back = False

    def __enter__(self) -> "_TxConnection":
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None

    def cursor(self) -> _TxCursor:
        return self._cursor

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True


def _connect_tx_factory(rows: list[dict[str, object]]):
    def _connect(*args: object, **kwargs: object) -> _TxConnection:
        return _TxConnection(rows)

    return _connect


def _tx_row(
    chat_id: str, thread_id: str, title: str | None, active: bool
) -> dict[str, object]:
    return {
        "chat_id": chat_id,
        "thread_id": thread_id,
        "title": title,
        "active": active,
        "created_at": datetime.now(UTC),
    }


# ---------------------------------------------------------------------------
# get_or_create_thread_id — REQ-001 (refactored to honor `active`)
# ---------------------------------------------------------------------------


def test_get_or_create_thread_id_creates_active_thread_for_unseen_chat(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("POSTGRES_URI", "postgresql://fake")
    rows: list[dict[str, object]] = []
    monkeypatch.setattr(thread_repository.psycopg, "connect", _connect_tx_factory(rows))

    thread_id = thread_repository.get_or_create_thread_id("chat-1")

    assert thread_id
    assert len(rows) == 1
    assert rows[0] == {
        "chat_id": "chat-1",
        "thread_id": thread_id,
        "title": None,
        "active": True,
        "created_at": rows[0]["created_at"],
    }

    second = thread_repository.get_or_create_thread_id("chat-1")
    assert second == thread_id


def test_get_or_create_thread_id_creates_new_when_no_row_is_active(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("POSTGRES_URI", "postgresql://fake")
    rows: list[dict[str, object]] = [_tx_row("chat-1", "T-old", None, False)]
    monkeypatch.setattr(thread_repository.psycopg, "connect", _connect_tx_factory(rows))

    thread_id = thread_repository.get_or_create_thread_id("chat-1")

    assert thread_id != "T-old"
    assert len(rows) == 2
    new_row = next(r for r in rows if r["thread_id"] == thread_id)
    assert new_row["active"] is True


def test_get_or_create_thread_id_returns_active_row_without_inserting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("POSTGRES_URI", "postgresql://fake")
    rows: list[dict[str, object]] = [
        _tx_row("chat-1", "T1", None, True),
        _tx_row("chat-1", "T2", None, False),
    ]
    monkeypatch.setattr(thread_repository.psycopg, "connect", _connect_tx_factory(rows))

    thread_id = thread_repository.get_or_create_thread_id("chat-1")

    assert thread_id == "T1"
    assert len(rows) == 2


# ---------------------------------------------------------------------------
# set_active_thread — REQ-005
# ---------------------------------------------------------------------------


def test_set_active_thread_swaps_active_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POSTGRES_URI", "postgresql://fake")
    rows: list[dict[str, object]] = [
        _tx_row("123", "T1", None, True),
        _tx_row("123", "T2", None, False),
    ]
    monkeypatch.setattr(thread_repository.psycopg, "connect", _connect_tx_factory(rows))

    result = thread_repository.set_active_thread("123", "T2")

    assert result is True
    t1 = next(r for r in rows if r["thread_id"] == "T1")
    t2 = next(r for r in rows if r["thread_id"] == "T2")
    assert t1["active"] is False
    assert t2["active"] is True


def test_set_active_thread_missing_target_returns_false_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("POSTGRES_URI", "postgresql://fake")
    rows: list[dict[str, object]] = [_tx_row("123", "T1", None, True)]
    monkeypatch.setattr(thread_repository.psycopg, "connect", _connect_tx_factory(rows))

    result = thread_repository.set_active_thread("123", "TX")

    assert result is False
    assert len(rows) == 1
    assert rows[0]["thread_id"] == "T1"
    assert rows[0]["active"] is True


# ---------------------------------------------------------------------------
# create_thread_for_chat — REQ-006
# ---------------------------------------------------------------------------


def test_create_thread_for_chat_deactivates_previous_and_inserts_active(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("POSTGRES_URI", "postgresql://fake")
    rows: list[dict[str, object]] = [_tx_row("123", "T-old", None, True)]
    monkeypatch.setattr(thread_repository.psycopg, "connect", _connect_tx_factory(rows))

    thread_id = thread_repository.create_thread_for_chat("123", title="pagamentos")

    assert thread_id
    old = next(r for r in rows if r["thread_id"] == "T-old")
    new = next(r for r in rows if r["thread_id"] == thread_id)
    assert old["active"] is False
    assert new["active"] is True
    assert new["title"] == "pagamentos"


def test_create_thread_for_chat_duplicate_title_raises_without_inserting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("POSTGRES_URI", "postgresql://fake")
    rows: list[dict[str, object]] = [_tx_row("123", "T1", "pagamentos", True)]
    monkeypatch.setattr(thread_repository.psycopg, "connect", _connect_tx_factory(rows))

    with pytest.raises(ValueError):
        thread_repository.create_thread_for_chat("123", title="pagamentos")

    assert len(rows) == 1


def test_create_thread_for_chat_without_title_inserts_null_title(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("POSTGRES_URI", "postgresql://fake")
    rows: list[dict[str, object]] = []
    monkeypatch.setattr(thread_repository.psycopg, "connect", _connect_tx_factory(rows))

    thread_id = thread_repository.create_thread_for_chat("123")

    assert thread_id
    assert len(rows) == 1
    assert rows[0]["title"] is None
    assert rows[0]["active"] is True


# ---------------------------------------------------------------------------
# "Restart preserva thread ativa" — REQ-007 (telegram-slash-commands-spec)
# ---------------------------------------------------------------------------


def test_get_or_create_thread_id_survives_new_connection_after_set_active(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("POSTGRES_URI", "postgresql://fake")
    rows: list[dict[str, object]] = [
        _tx_row("123", "T1", None, False),
        _tx_row("123", "T2", None, True),
    ]
    monkeypatch.setattr(thread_repository.psycopg, "connect", _connect_tx_factory(rows))

    assert thread_repository.set_active_thread("123", "T1") is True

    # Simulate a process restart: a brand new connection object, same underlying rows.
    new_connection = thread_repository.psycopg.connect("postgresql://fake")
    monkeypatch.setattr(thread_repository.psycopg, "connect", lambda *a, **kw: new_connection)

    result = thread_repository.get_or_create_thread_id("123")

    assert result == "T1"


# ============================================================================
# Fake multi-row table for list_threads_for_chat / update_thread_title /
# get_thread_by_title — dispatch by SQL shape (LIMIT 20 / UPDATE / plain
# SELECT), since these operate over several rows per chat_id instead of the
# single chat_id -> thread_id mapping used by get_or_create_thread_id above.
# ============================================================================


class _MultiRowCursor:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows
        self._last_result: object = None
        self.rowcount = 0

    def __enter__(self) -> "_MultiRowCursor":
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None

    def execute(self, query: str, params: tuple) -> None:
        query = query.strip()
        if query.startswith("SELECT") and "LIMIT 20" in query:
            (chat_id,) = params
            matches = [r for r in self._rows if r["chat_id"] == chat_id]
            matches.sort(key=lambda r: r["created_at"], reverse=True)
            self._last_result = [
                (r["thread_id"], r["title"], r["active"], r["created_at"])
                for r in matches[:20]
            ]
        elif query.startswith("SELECT") and "!=" in query:
            chat_id, title, exclude_thread_id = params
            conflict = any(
                r["chat_id"] == chat_id
                and r["title"] == title
                and r["thread_id"] != exclude_thread_id
                for r in self._rows
            )
            self._last_result = (1,) if conflict else None
        elif query.startswith("UPDATE"):
            title, chat_id, thread_id = params
            target = next(
                (
                    r
                    for r in self._rows
                    if r["chat_id"] == chat_id and r["thread_id"] == thread_id
                ),
                None,
            )
            if target is not None:
                target["title"] = title
                self.rowcount = 1
            else:
                self.rowcount = 0
        elif query.startswith("SELECT"):
            chat_id, title = params
            match = next(
                (
                    r
                    for r in self._rows
                    if r["chat_id"] == chat_id and r["title"] == title
                ),
                None,
            )
            self._last_result = (
                (match["thread_id"], match["title"], match["active"], match["created_at"])
                if match is not None
                else None
            )
        else:
            raise AssertionError(f"Query inesperada no fake cursor: {query!r}")

    def fetchone(self) -> object:
        return self._last_result

    def fetchall(self) -> list[object]:
        return self._last_result if self._last_result is not None else []


class _MultiRowConnection:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._cursor = _MultiRowCursor(rows)

    def __enter__(self) -> "_MultiRowConnection":
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None

    def cursor(self) -> _MultiRowCursor:
        return self._cursor


def _connect_multi_row_factory(rows: list[dict[str, object]]):
    def _connect(*args: object, **kwargs: object) -> _MultiRowConnection:
        return _MultiRowConnection(rows)

    return _connect


def _row(chat_id: str, thread_id: str, title: str | None, active: bool, created_at: datetime) -> dict[str, object]:
    return {
        "chat_id": chat_id,
        "thread_id": thread_id,
        "title": title,
        "active": active,
        "created_at": created_at,
    }


# ---------------------------------------------------------------------------
# list_threads_for_chat — REQ-002
# ---------------------------------------------------------------------------


def test_list_threads_for_chat_orders_by_created_at_desc(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POSTGRES_URI", "postgresql://fake")
    now = datetime.now(UTC)
    rows = [
        _row("123", "A", None, False, now),
        _row("123", "B", None, False, now - timedelta(days=1)),
        _row("123", "C", None, False, now - timedelta(days=7)),
    ]
    monkeypatch.setattr(thread_repository.psycopg, "connect", _connect_multi_row_factory(rows))

    result = thread_repository.list_threads_for_chat("123")

    assert [r["thread_id"] for r in result] == ["A", "B", "C"]
    assert set(result[0].keys()) == {"thread_id", "title", "active", "created_at"}


def test_list_threads_for_chat_limits_to_20(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POSTGRES_URI", "postgresql://fake")
    now = datetime.now(UTC)
    rows = [
        _row("123", f"T{i}", None, False, now - timedelta(minutes=i)) for i in range(25)
    ]
    monkeypatch.setattr(thread_repository.psycopg, "connect", _connect_multi_row_factory(rows))

    result = thread_repository.list_threads_for_chat("123")

    assert len(result) == 20
    returned_ids = {r["thread_id"] for r in result}
    for old in ("T20", "T21", "T22", "T23", "T24"):
        assert old not in returned_ids


def test_list_threads_for_chat_empty_returns_empty_list(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POSTGRES_URI", "postgresql://fake")
    monkeypatch.setattr(thread_repository.psycopg, "connect", _connect_multi_row_factory([]))

    result = thread_repository.list_threads_for_chat("999")

    assert result == []


# ---------------------------------------------------------------------------
# update_thread_title — REQ-003
# ---------------------------------------------------------------------------


def test_update_thread_title_updates_free_title(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POSTGRES_URI", "postgresql://fake")
    rows = [_row("123", "T1", None, True, datetime.now(UTC))]
    monkeypatch.setattr(thread_repository.psycopg, "connect", _connect_multi_row_factory(rows))

    result = thread_repository.update_thread_title("T1", "123", "pagamentos")

    assert result is True
    assert rows[0]["title"] == "pagamentos"


def test_update_thread_title_missing_row_returns_false(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POSTGRES_URI", "postgresql://fake")
    rows: list[dict[str, object]] = []
    monkeypatch.setattr(thread_repository.psycopg, "connect", _connect_multi_row_factory(rows))

    result = thread_repository.update_thread_title("TX", "123", "x")

    assert result is False


def test_update_thread_title_duplicate_raises_value_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POSTGRES_URI", "postgresql://fake")
    rows = [
        _row("123", "T1", None, True, datetime.now(UTC)),
        _row("123", "T2", "compras", False, datetime.now(UTC)),
    ]
    monkeypatch.setattr(thread_repository.psycopg, "connect", _connect_multi_row_factory(rows))

    with pytest.raises(ValueError):
        thread_repository.update_thread_title("T1", "123", "compras")

    assert rows[0]["title"] is None
    assert rows[1]["title"] == "compras"


# ---------------------------------------------------------------------------
# get_thread_by_title — REQ-004
# ---------------------------------------------------------------------------


def test_get_thread_by_title_existing_returns_dict(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POSTGRES_URI", "postgresql://fake")
    rows = [_row("123", "T1", "pagamentos", True, datetime.now(UTC))]
    monkeypatch.setattr(thread_repository.psycopg, "connect", _connect_multi_row_factory(rows))

    result = thread_repository.get_thread_by_title("123", "pagamentos")

    assert result is not None
    assert result["title"] == "pagamentos"
    assert result["thread_id"] == "T1"


def test_get_thread_by_title_missing_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POSTGRES_URI", "postgresql://fake")
    monkeypatch.setattr(thread_repository.psycopg, "connect", _connect_multi_row_factory([]))

    result = thread_repository.get_thread_by_title("123", "inexistente")

    assert result is None


def test_get_thread_by_title_same_title_different_chat_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("POSTGRES_URI", "postgresql://fake")
    rows = [_row("456", "T1", "pagamentos", True, datetime.now(UTC))]
    monkeypatch.setattr(thread_repository.psycopg, "connect", _connect_multi_row_factory(rows))

    result = thread_repository.get_thread_by_title("123", "pagamentos")

    assert result is None
