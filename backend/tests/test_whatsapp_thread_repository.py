"""Testes de `src/infrastructure/whatsapp/thread_repository.py` (get_or_create_thread_id).

Cobre a task `whatsapp-evolution-channel-task-channel-2` (whatsapp-channel
REQ-002), mesmo padrão de `test_telegram_thread_repository.py` simplificado
para um único `thread_id` por `phone_number` (sem `active`/`title` — fora de
escopo deste change).
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.infrastructure.whatsapp import thread_repository


class _FakeCursor:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows
        self._last_result: object = None

    def __enter__(self) -> "_FakeCursor":
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None

    def execute(self, query: str, params: tuple) -> None:
        q = query.strip()
        if q.startswith("SELECT thread_id FROM whatsapp_threads"):
            (phone_number,) = params
            match = next(
                (r for r in self._rows if r["phone_number"] == phone_number), None
            )
            self._last_result = (match["thread_id"],) if match is not None else None
        elif q.startswith("INSERT INTO whatsapp_threads"):
            phone_number, thread_id = params
            self._rows.append(
                {
                    "phone_number": phone_number,
                    "thread_id": thread_id,
                    "created_at": datetime.now(UTC),
                }
            )
        else:
            raise AssertionError(f"Query inesperada no fake cursor: {query!r}")

    def fetchone(self) -> object:
        return self._last_result


class _FakeConnection:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._cursor = _FakeCursor(rows)
        self.committed = False

    def __enter__(self) -> "_FakeConnection":
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None

    def cursor(self) -> _FakeCursor:
        return self._cursor

    def commit(self) -> None:
        self.committed = True


def _connect_factory(rows: list[dict[str, object]]):
    def _connect(*args: object, **kwargs: object) -> _FakeConnection:
        return _FakeConnection(rows)

    return _connect


# ---------------------------------------------------------------------------
# get_or_create_thread_id — REQ-002
# whatsapp-evolution-channel-task-channel-2-unit-1 / unit-2
# ---------------------------------------------------------------------------


def test_get_or_create_thread_id_creates_new_thread_for_unseen_phone_number(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """whatsapp-evolution-channel-task-channel-2-unit-1."""
    monkeypatch.setenv("POSTGRES_URI", "postgresql://fake")
    rows: list[dict[str, object]] = []
    monkeypatch.setattr(thread_repository.psycopg, "connect", _connect_factory(rows))

    thread_id = thread_repository.get_or_create_thread_id("+5511999990000")

    assert thread_id
    assert len(rows) == 1
    assert rows[0]["phone_number"] == "+5511999990000"
    assert rows[0]["thread_id"] == thread_id


def test_get_or_create_thread_id_returns_existing_thread_without_inserting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """whatsapp-evolution-channel-task-channel-2-unit-2."""
    monkeypatch.setenv("POSTGRES_URI", "postgresql://fake")
    rows: list[dict[str, object]] = [
        {
            "phone_number": "+5511999990000",
            "thread_id": "existing-thread",
            "created_at": datetime.now(UTC),
        }
    ]
    monkeypatch.setattr(thread_repository.psycopg, "connect", _connect_factory(rows))

    thread_id = thread_repository.get_or_create_thread_id("+5511999990000")

    assert thread_id == "existing-thread"
    assert len(rows) == 1
