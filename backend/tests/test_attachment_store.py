"""Testes de `attachments.store` (chat-file-attachment REQ-004).

Espelha o estilo assíncrono de `test_auth_sessions.py`: pool/conexão/cursor
fake para não depender de Postgres real; grava em `tmp_path` no disco.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from src.infrastructure.attachments import store


class _FakeCursor:
    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple | None]] = []

    async def __aenter__(self) -> "_FakeCursor":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return None

    async def execute(self, query: str, params: tuple | None = None) -> None:
        self.executed.append((query, params))


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


async def test_store_attachment_writes_file_and_inserts_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """REQ-004: grava em {output_dir}/{thread_id}/{attachment_id}.{ext} e insere
    exatamente uma linha em chat_attachments com thread_id/user_id/filename/
    content_type/size_bytes corretos."""
    cursor = _FakeCursor()
    _patch_pool(monkeypatch, cursor)
    data = b"%PDF-1.4 fake pdf bytes"

    result = await store.store_attachment(
        thread_id="thread-123",
        user_id="user-abc",
        data=data,
        filename="report.pdf",
        content_type="application/pdf",
        output_dir=tmp_path,
    )

    saved_path = Path(result.storage_path)
    assert saved_path.exists()
    assert saved_path.parent == tmp_path / "thread-123"
    assert saved_path.suffix == ".pdf"
    assert saved_path.read_bytes() == data

    inserts = [(q, p) for q, p in cursor.executed if q.strip().startswith("INSERT")]
    assert len(inserts) == 1
    query, params = inserts[0]
    assert "INSERT INTO chat_attachments" in query
    assert params is not None
    assert params[1] == "thread-123"
    assert params[2] == "user-abc"
    assert params[3] == "report.pdf"
    assert params[4] == "application/pdf"
    assert params[5] == len(data)


async def test_store_attachment_generates_id_not_trusting_client_filename(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """O nome em disco é sempre `{attachment_id}{extensão}` — nunca o filename do cliente."""
    cursor = _FakeCursor()
    _patch_pool(monkeypatch, cursor)

    result = await store.store_attachment(
        thread_id="thread-123",
        user_id="user-abc",
        data=b"hello",
        filename="../../etc/passwd",
        content_type="text/plain",
        output_dir=tmp_path,
    )

    saved_path = Path(result.storage_path)
    assert saved_path.name != "../../etc/passwd"
    assert saved_path.name == f"{result.attachment_id}.txt"
