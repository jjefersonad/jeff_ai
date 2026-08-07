"""Testes de `src/infrastructure/auth/users.py` (leitura de usuários)."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.infrastructure.auth import users


class _FakeCursor:
    def __init__(self, fetchone_result: tuple | None = None) -> None:
        self.executed: list[tuple[str, tuple | None]] = []
        self._fetchone_result = fetchone_result

    async def __aenter__(self) -> "_FakeCursor":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return None

    async def execute(self, query: str, params: tuple | None = None) -> None:
        self.executed.append((query, params))

    async def fetchone(self) -> tuple | None:
        return self._fetchone_result


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
    monkeypatch.setattr(users, "get_pool", lambda: _FakePool(cursor))


async def test_get_user_by_username_returns_none_when_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cursor = _FakeCursor(fetchone_result=None)
    _patch_pool(monkeypatch, cursor)

    result = await users.get_user_by_username("ghost")

    assert result is None
    query, params = cursor.executed[0]
    assert "SELECT" in query
    assert "FROM users" in query
    assert params == ("ghost",)


async def test_get_user_by_username_returns_user_when_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created = datetime(2026, 1, 1, tzinfo=timezone.utc)
    cursor = _FakeCursor(
        fetchone_result=("id-1", "alice", "hashed-pw", "admin", True, created)
    )
    _patch_pool(monkeypatch, cursor)

    result = await users.get_user_by_username("alice")

    assert result == users.User(
        id="id-1",
        username="alice",
        password_hash="hashed-pw",
        role="admin",
        is_active=True,
        created_at=created,
    )


# ---------------------------------------------------------------------------
# user-management task-api-2 — create_user()
# ---------------------------------------------------------------------------


async def test_create_user_inserts_and_returns_created_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created = datetime(2026, 1, 3, tzinfo=timezone.utc)
    cursor = _FakeCursor(
        fetchone_result=("id-new", "newbie", "bcrypt-hash", "user", True, created)
    )
    _patch_pool(monkeypatch, cursor)

    result = await users.create_user(
        username="newbie", password_hash="bcrypt-hash", role="user"
    )

    assert result == users.User(
        id="id-new",
        username="newbie",
        password_hash="bcrypt-hash",
        role="user",
        is_active=True,
        created_at=created,
    )
    query, params = cursor.executed[0]
    assert "INSERT INTO users" in query
    assert "RETURNING" in query
    assert params == ("newbie", "bcrypt-hash", "user")


async def test_create_user_defaults_role_to_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created = datetime(2026, 1, 3, tzinfo=timezone.utc)
    cursor = _FakeCursor(
        fetchone_result=("id-new", "newbie", "bcrypt-hash", "user", True, created)
    )
    _patch_pool(monkeypatch, cursor)

    await users.create_user(username="newbie", password_hash="bcrypt-hash")

    _query, params = cursor.executed[0]
    assert params == ("newbie", "bcrypt-hash", "user")


# ---------------------------------------------------------------------------
# user-management task-core-2 (resgate em api-1) — list_users() e created_at.
# `core-2` foi arquivado sem entregar `list_users()`; como `api-1` depende
# dele, estes testes são o RED que força a entrega agora.
# ---------------------------------------------------------------------------


class _FakeFetchAllCursor:
    """Cursor fake para `SELECT ... ORDER BY ...` consumido via `fetchall`."""

    def __init__(self, fetchall_result: list[tuple]) -> None:
        self.executed: list[tuple[str, tuple | None]] = []
        self._fetchall_result = fetchall_result

    async def __aenter__(self) -> "_FakeFetchAllCursor":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return None

    async def execute(self, query: str, params: tuple | None = None) -> None:
        self.executed.append((query, params))

    async def fetchall(self) -> list[tuple]:
        return list(self._fetchall_result)


class _FakeFetchAllConnection:
    def __init__(self, cursor: _FakeFetchAllCursor) -> None:
        self._cursor = cursor

    async def __aenter__(self) -> "_FakeFetchAllConnection":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return None

    def cursor(self) -> _FakeFetchAllCursor:
        return self._cursor


class _FakeFetchAllPool:
    def __init__(self, cursor: _FakeFetchAllCursor) -> None:
        self._cursor = cursor

    def connection(self) -> _FakeFetchAllConnection:
        return _FakeFetchAllConnection(self._cursor)


def _patch_pool_fetchall(
    monkeypatch: pytest.MonkeyPatch, cursor: _FakeFetchAllCursor
) -> None:
    monkeypatch.setattr(users, "get_pool", lambda: _FakeFetchAllPool(cursor))


async def test_list_users_returns_all_users_including_inactive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REQ-001 (api): lista inclui inativos; ordem determinística (ORDER BY)."""
    created_a = datetime(2026, 1, 1, tzinfo=timezone.utc)
    created_b = datetime(2026, 1, 2, tzinfo=timezone.utc)
    cursor = _FakeFetchAllCursor(
        fetchall_result=[
            ("id-1", "alice", "hashed-a", "admin", True, created_a),
            ("id-2", "bob", "hashed-b", "user", False, created_b),
        ]
    )
    _patch_pool_fetchall(monkeypatch, cursor)

    result = await users.list_users()

    assert result == [
        users.User(
            id="id-1",
            username="alice",
            password_hash="hashed-a",
            role="admin",
            is_active=True,
            created_at=created_a,
        ),
        users.User(
            id="id-2",
            username="bob",
            password_hash="hashed-b",
            role="user",
            is_active=False,
            created_at=created_b,
        ),
    ]
    query, _params = cursor.executed[0]
    # Sem WHERE — deve devolver todos os usuários (incluindo inativos).
    assert "SELECT" in query
    assert "FROM users" in query
    assert "WHERE" not in query
    # Ordem determinística para que o GET /admin/users seja estável.
    assert "ORDER BY" in query


async def test_list_users_returns_empty_list_when_no_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cursor = _FakeFetchAllCursor(fetchall_result=[])
    _patch_pool_fetchall(monkeypatch, cursor)

    result = await users.list_users()

    assert result == []


# ---------------------------------------------------------------------------
# user-management task-core-3 (resgate em api-3) — update_user() e o
# guarda-corpo de auto-lockout. `core-3` foi arquivado sem entregar
# `update_user()`; como `api-3` depende dele, estes testes são o RED que
# força a entrega agora — mesmo padrão já visto em `core-2`/`api-1`.
# ---------------------------------------------------------------------------


class _FakeSequentialCursor:
    """Cursor fake cujo `fetchone` devolve um resultado da fila a cada chamada.

    `update_user` roda mais de uma query (checagem do guarda-corpo, depois o
    `UPDATE ... RETURNING`) — `_FakeCursor` (um único `fetchone_result` fixo)
    não serve para isso.
    """

    def __init__(self, fetchone_results: list[tuple | None]) -> None:
        self.executed: list[tuple[str, tuple | None]] = []
        self._results = list(fetchone_results)

    async def __aenter__(self) -> "_FakeSequentialCursor":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return None

    async def execute(self, query: str, params: tuple | None = None) -> None:
        self.executed.append((query, params))

    async def fetchone(self) -> tuple | None:
        return self._results.pop(0)


def _patch_pool_sequential(
    monkeypatch: pytest.MonkeyPatch, cursor: _FakeSequentialCursor
) -> None:
    monkeypatch.setattr(users, "get_pool", lambda: _FakePool(cursor))


async def test_update_user_normal_update_changes_role(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REQ-003: alvo diferente do caller, não é o último admin — atualiza normalmente."""
    created = datetime(2026, 1, 1, tzinfo=timezone.utc)
    cursor = _FakeSequentialCursor(
        fetchone_results=[
            ("target-1", "bob", "hashed-b", "admin", True, created),
        ]
    )
    _patch_pool_sequential(monkeypatch, cursor)

    result = await users.update_user("target-1", role="admin", caller_id="admin-1")

    assert result == users.User(
        id="target-1",
        username="bob",
        password_hash="hashed-b",
        role="admin",
        is_active=True,
        created_at=created,
    )
    query, params = cursor.executed[0]
    assert "UPDATE users" in query
    assert "RETURNING" in query
    assert params == ("admin", "target-1")


async def test_update_user_rejects_self_deactivation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REQ-004: caller tenta se auto-desativar — rejeitado, nenhuma query de escrita roda."""
    cursor = _FakeSequentialCursor(fetchone_results=[])
    _patch_pool_sequential(monkeypatch, cursor)

    with pytest.raises(users.SelfLockoutError):
        await users.update_user("admin-1", is_active=False, caller_id="admin-1")

    assert cursor.executed == []


async def test_update_user_rejects_self_demotion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REQ-004: caller tenta se auto-rebaixar pra `role=user` — rejeitado."""
    cursor = _FakeSequentialCursor(fetchone_results=[])
    _patch_pool_sequential(monkeypatch, cursor)

    with pytest.raises(users.SelfLockoutError):
        await users.update_user("admin-1", role="user", caller_id="admin-1")

    assert cursor.executed == []


async def test_update_user_rejects_deactivating_last_active_admin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REQ-004: alvo é o único role=admin/is_active=true restante — rejeitado."""
    created = datetime(2026, 1, 1, tzinfo=timezone.utc)
    cursor = _FakeSequentialCursor(
        fetchone_results=[
            (1,),  # SELECT count(*) admins ativos
            ("target-1", "carol", "hashed-c", "admin", True, created),  # SELECT alvo
        ]
    )
    _patch_pool_sequential(monkeypatch, cursor)

    with pytest.raises(users.LastAdminError):
        await users.update_user("target-1", is_active=False, caller_id="admin-1")

    # Nenhum UPDATE foi emitido — só as duas queries de checagem.
    assert len(cursor.executed) == 2
    assert all("UPDATE users" not in q for q, _ in cursor.executed)


async def test_update_user_allows_deactivating_admin_when_another_is_active(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Existe um segundo admin ativo — a mesma mudança já é permitida."""
    created = datetime(2026, 1, 1, tzinfo=timezone.utc)
    cursor = _FakeSequentialCursor(
        fetchone_results=[
            (2,),  # SELECT count(*) admins ativos — dois
            ("target-1", "carol", "hashed-c", "admin", True, created),  # SELECT alvo
            ("target-1", "carol", "hashed-c", "admin", False, created),  # UPDATE ... RETURNING
        ]
    )
    _patch_pool_sequential(monkeypatch, cursor)

    result = await users.update_user("target-1", is_active=False, caller_id="admin-2")

    assert result.is_active is False
    assert any("UPDATE users" in q for q, _ in cursor.executed)
