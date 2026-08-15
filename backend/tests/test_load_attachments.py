"""load_attachments — session-file-sandbox attach-1 unit-1 (REQ-002)."""
from __future__ import annotations

import pytest

from src.infrastructure.attachments import store


class _FakeCursor:
    """Simula SELECT filtrado por id + thread_id + user_id (REQ-002)."""

    def __init__(self, rows_by_id: dict[str, tuple] | None = None) -> None:
        self._rows_by_id = rows_by_id or {}
        self.executed: list[tuple[str, tuple | None]] = []
        self._last_params: tuple | None = None

    async def __aenter__(self) -> "_FakeCursor":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return None

    async def execute(self, query: str, params: tuple | None = None) -> None:
        self.executed.append((query, params))
        self._last_params = params

    async def fetchone(self) -> tuple | None:
        if not self._last_params or len(self._last_params) < 3:
            return None
        attachment_id, thread_id, user_id = (
            str(self._last_params[0]),
            str(self._last_params[1]),
            str(self._last_params[2]),
        )
        row = self._rows_by_id.get(attachment_id)
        if row is None:
            return None
        # row = (id, user_id, thread_id, filename, content_type, size, path)
        if str(row[1]) != user_id or str(row[2]) != thread_id:
            return None
        return row


class _FakeConnection:
    def __init__(self, cursor: _FakeCursor) -> None:
        self._cursor = cursor

    async def __aenter__(self) -> "_FakeConnection":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return None

    def cursor(self) -> _FakeCursor:
        return self._cursor


class _FakePool:
    def __init__(self, cursor: _FakeCursor) -> None:
        self._cursor = cursor

    def connection(self) -> _FakeConnection:
        return _FakeConnection(self._cursor)


def _patch_pool(monkeypatch: pytest.MonkeyPatch, cursor: _FakeCursor) -> None:
    monkeypatch.setattr(store, "get_pool", lambda: _FakePool(cursor))


def _row(
    *,
    attachment_id: str,
    user_id: str,
    thread_id: str,
    filename: str = "logo.png",
    content_type: str = "image/png",
    storage_path: str = "/files/user-a/attachment/logo.png",
) -> tuple:
    return (
        attachment_id,
        user_id,
        thread_id,
        filename,
        content_type,
        12,
        storage_path,
    )


@pytest.mark.asyncio
async def test_load_attachments_returns_owned_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Owned id matching thread+user returns StoredAttachment with storage_path."""
    row = _row(
        attachment_id="att-1",
        user_id="user-a",
        thread_id="thread-1",
        storage_path="/files/user-a/attachment/att-1.png",
    )
    cursor = _FakeCursor({"att-1": row})
    _patch_pool(monkeypatch, cursor)

    result = await store.load_attachments(
        ["att-1"], thread_id="thread-1", user_id="user-a"
    )

    assert len(result) == 1
    assert result[0] is not None
    assert result[0].attachment_id == "att-1"
    assert result[0].storage_path == "/files/user-a/attachment/att-1.png"
    assert result[0].filename == "logo.png"
    assert result[0].content_type == "image/png"


@pytest.mark.asyncio
async def test_load_attachments_other_thread_is_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WHEN id belongs to another thread THEN slot is None and path not exposed."""
    # Row exists in DB for a different thread — filter must reject it.
    row = _row(
        attachment_id="att-other-thread",
        user_id="user-a",
        thread_id="thread-OTHER",
        storage_path="/files/user-a/attachment/secret.png",
    )
    cursor = _FakeCursor({"att-other-thread": row})
    _patch_pool(monkeypatch, cursor)

    result = await store.load_attachments(
        ["att-other-thread"], thread_id="thread-1", user_id="user-a"
    )

    assert result == [None]
    # Query must constrain thread_id + user_id (not only id).
    assert cursor.executed
    _query, params = cursor.executed[0]
    assert params is not None
    assert "thread-1" in params
    assert "user-a" in params


@pytest.mark.asyncio
async def test_load_attachments_other_user_is_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WHEN id belongs to another user_id THEN slot is None (spoof isolation)."""
    row = _row(
        attachment_id="att-other-user",
        user_id="user-B",
        thread_id="thread-1",
        storage_path="/files/user-B/attachment/secret.png",
    )
    cursor = _FakeCursor({"att-other-user": row})
    _patch_pool(monkeypatch, cursor)

    result = await store.load_attachments(
        ["att-other-user"], thread_id="thread-1", user_id="user-a"
    )

    assert result == [None]


@pytest.mark.asyncio
async def test_load_attachments_missing_id_is_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cursor = _FakeCursor({})
    _patch_pool(monkeypatch, cursor)

    result = await store.load_attachments(
        ["missing"], thread_id="thread-1", user_id="user-a"
    )

    assert result == [None]


@pytest.mark.asyncio
async def test_load_attachments_preserves_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = {
        "att-1": _row(
            attachment_id="att-1",
            user_id="user-a",
            thread_id="thread-1",
            filename="a.png",
            storage_path="/files/user-a/attachment/a.png",
        ),
        "att-2": _row(
            attachment_id="att-2",
            user_id="user-a",
            thread_id="thread-1",
            filename="b.png",
            storage_path="/files/user-a/attachment/b.png",
        ),
    }
    cursor = _FakeCursor(rows)
    _patch_pool(monkeypatch, cursor)

    result = await store.load_attachments(
        ["att-2", "missing", "att-1"], thread_id="thread-1", user_id="user-a"
    )

    assert result[0] is not None and result[0].attachment_id == "att-2"
    assert result[1] is None
    assert result[2] is not None and result[2].attachment_id == "att-1"
