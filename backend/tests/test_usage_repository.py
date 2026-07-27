"""Testes de `src/infrastructure/usage/repository.py` (record + aggregate)."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from src.infrastructure.usage import repository

# ============================================================================
# In-memory fake of `token_usage_events` for record / aggregate.
# ============================================================================


class _UsageCursor:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows
        self._last_result: object = None
        self.executed: list[tuple[str, tuple | None]] = []

    def __enter__(self) -> "_UsageCursor":
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None

    def execute(self, query: str, params: tuple | None = None) -> None:
        self.executed.append((query, params))
        q = " ".join(query.split())
        if q.upper().startswith("INSERT INTO TOKEN_USAGE_EVENTS"):
            assert params is not None
            (
                user_key,
                thread_id,
                provider,
                model,
                prompt_tokens,
                completion_tokens,
                total_tokens,
                source,
            ) = params
            self._rows.append(
                {
                    "user_key": user_key,
                    "thread_id": thread_id,
                    "provider": provider,
                    "model": model,
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": total_tokens,
                    "source": source,
                    "created_at": datetime.now(UTC),
                }
            )
            return

        if "SUM(" in q.upper() and "FROM TOKEN_USAGE_EVENTS" in q.upper():
            assert params is not None
            filtered = list(self._rows)
            # Params order matches repository: user_key?, from?, to?, provider?, model?
            # We inspect the SQL for which filters are present.
            param_iter = iter(params)
            if "user_key = %s" in q:
                uk = next(param_iter)
                filtered = [r for r in filtered if r["user_key"] == uk]
            if "created_at >=" in q or "created_at >= %s" in q:
                from_ts = next(param_iter)
                filtered = [r for r in filtered if r["created_at"] >= from_ts]
            if "created_at <=" in q or "created_at <= %s" in q:
                to_ts = next(param_iter)
                filtered = [r for r in filtered if r["created_at"] <= to_ts]
            if "provider = %s" in q:
                provider = next(param_iter)
                filtered = [r for r in filtered if r["provider"] == provider]
            if "model = %s" in q:
                model = next(param_iter)
                filtered = [r for r in filtered if r["model"] == model]

            prompt = sum((r["prompt_tokens"] or 0) for r in filtered)  # type: ignore[operator]
            completion = sum((r["completion_tokens"] or 0) for r in filtered)  # type: ignore[operator]
            total = sum((r["total_tokens"] or 0) for r in filtered)  # type: ignore[operator]
            self._last_result = (prompt, completion, total)
            return

        raise AssertionError(f"Query inesperada no fake usage cursor: {query!r}")

    def fetchone(self) -> object:
        return self._last_result


class _UsageConnection:
    def __init__(self, rows: list[dict[str, object]], *, fail_on_execute: bool = False) -> None:
        self._rows = rows
        self._fail_on_execute = fail_on_execute
        self._cursor = _UsageCursor(rows)
        self.committed = False

    def __enter__(self) -> "_UsageConnection":
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None

    def cursor(self) -> _UsageCursor:
        if self._fail_on_execute:
            return _FailingCursor()
        return self._cursor

    def commit(self) -> None:
        self.committed = True


class _FailingCursor:
    def __enter__(self) -> "_FailingCursor":
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None

    def execute(self, query: str, params: tuple | None = None) -> None:
        raise OSError("simulated database failure")

    def fetchone(self) -> object:
        raise AssertionError("fetchone não deve ser chamado após falha")


def _connect_factory(rows: list[dict[str, object]], *, fail_on_execute: bool = False):
    def _connect(*args: object, **kwargs: object) -> _UsageConnection:
        return _UsageConnection(rows, fail_on_execute=fail_on_execute)

    return _connect


def test_record_persists_complete_event(monkeypatch: pytest.MonkeyPatch) -> None:
    rows: list[dict[str, object]] = []
    monkeypatch.setattr(repository.psycopg, "connect", _connect_factory(rows))

    repo = repository.UsageRepository("postgresql://fake")
    repo.record(
        user_key="web:abc",
        thread_id="thread-1",
        provider="ollama",
        model="minimax-m2.7:cloud",
        prompt_tokens=10,
        completion_tokens=20,
        total_tokens=30,
        source="chat",
    )

    assert len(rows) == 1
    event = rows[0]
    assert event["user_key"] == "web:abc"
    assert event["thread_id"] == "thread-1"
    assert event["provider"] == "ollama"
    assert event["model"] == "minimax-m2.7:cloud"
    assert event["prompt_tokens"] == 10
    assert event["completion_tokens"] == 20
    assert event["total_tokens"] == 30
    assert event["source"] == "chat"


def test_record_fail_open_does_not_propagate(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    rows: list[dict[str, object]] = []
    monkeypatch.setattr(
        repository.psycopg, "connect", _connect_factory(rows, fail_on_execute=True)
    )

    repo = repository.UsageRepository("postgresql://fake")
    with caplog.at_level("ERROR", logger="src.infrastructure.usage.repository"):
        repo.record(
            user_key="web:abc",
            thread_id="thread-1",
            provider="ollama",
            model="minimax-m2.7:cloud",
            prompt_tokens=1,
            completion_tokens=2,
            total_tokens=3,
            source="chat",
        )

    assert rows == []
    assert any("Failed to record token usage" in msg for msg in caplog.messages)


def test_aggregate_filters_and_empty_user(monkeypatch: pytest.MonkeyPatch) -> None:
    now = datetime.now(UTC)
    rows: list[dict[str, object]] = [
        {
            "user_key": "web:abc",
            "thread_id": "t1",
            "provider": "ollama",
            "model": "model-a",
            "prompt_tokens": 10,
            "completion_tokens": 20,
            "total_tokens": 30,
            "source": "chat",
            "created_at": now - timedelta(days=2),
        },
        {
            "user_key": "web:abc",
            "thread_id": "t1",
            "provider": "ollama",
            "model": "model-a",
            "prompt_tokens": 5,
            "completion_tokens": 5,
            "total_tokens": 10,
            "source": "chat",
            "created_at": now,
        },
        {
            "user_key": "web:abc",
            "thread_id": "t1",
            "provider": "ollama",
            "model": "model-b",
            "prompt_tokens": 100,
            "completion_tokens": 200,
            "total_tokens": 300,
            "source": "chat",
            "created_at": now,
        },
    ]
    monkeypatch.setattr(repository.psycopg, "connect", _connect_factory(rows))

    repo = repository.UsageRepository("postgresql://fake")
    filtered = repo.aggregate(
        user_key="web:abc",
        from_ts=now - timedelta(hours=1),
        to_ts=now + timedelta(hours=1),
        model="model-a",
    )
    assert filtered["prompt_tokens"] == 5
    assert filtered["completion_tokens"] == 5
    assert filtered["total_tokens"] == 10
    assert filtered["user_key"] == "web:abc"
    assert filtered["filters"]["model"] == "model-a"

    empty = repo.aggregate(user_key="web:nobody")
    assert empty["prompt_tokens"] == 0
    assert empty["completion_tokens"] == 0
    assert empty["total_tokens"] == 0
    assert empty["user_key"] == "web:nobody"
    # REQ-005: aggregate is read-only
    assert len(rows) == 3
