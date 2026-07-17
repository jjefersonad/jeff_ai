"""Testes de `src/infrastructure/auth/db.py` (pool de conexão dedicado)."""
from __future__ import annotations

from collections.abc import Iterator

import pytest

from src.infrastructure.auth import db


class _FakePool:
    def __init__(self, conninfo: str, open: bool = True) -> None:
        self.conninfo = conninfo
        self.opened = False
        self.closed = False

    async def open(self) -> None:
        self.opened = True

    async def close(self) -> None:
        self.closed = True


@pytest.fixture(autouse=True)
def _reset_pool() -> Iterator[None]:
    db._pool = None
    yield
    db._pool = None


async def test_init_pool_opens_and_registers_pool(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(db, "AsyncConnectionPool", _FakePool)

    pool = await db.init_pool("postgresql://fake")

    assert isinstance(pool, _FakePool)
    assert pool.opened is True
    assert db.get_pool() is pool


async def test_get_pool_raises_when_not_initialized() -> None:
    with pytest.raises(RuntimeError):
        db.get_pool()


async def test_close_pool_closes_and_clears_registration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(db, "AsyncConnectionPool", _FakePool)
    pool = await db.init_pool("postgresql://fake")

    await db.close_pool()

    assert pool.closed is True
    with pytest.raises(RuntimeError):
        db.get_pool()


async def test_close_pool_is_noop_when_not_initialized() -> None:
    await db.close_pool()
