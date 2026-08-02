"""Testes de `ownership.store` (media-ownership-authorization REQ-001, REQ-002).

Espelha o estilo assíncrono de `test_attachment_store.py`: pool/conexão/cursor
fake para não depender de Postgres real.
"""
from __future__ import annotations

import pytest

from src.domain.integrations import UserIntegration
from src.infrastructure.auth.users import User
from src.infrastructure.ownership import store


class _FakeCursor:
    def __init__(
        self,
        *,
        raise_on_execute: Exception | None = None,
        fetchone_result: tuple | None = None,
        fetchall_result: list[tuple] | None = None,
    ) -> None:
        self.executed: list[tuple[str, tuple | None]] = []
        self._raise_on_execute = raise_on_execute
        self._fetchone_result = fetchone_result
        self._fetchall_result = fetchall_result if fetchall_result is not None else []

    async def __aenter__(self) -> "_FakeCursor":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return None

    async def execute(self, query: str, params: tuple | None = None) -> None:
        if self._raise_on_execute is not None:
            raise self._raise_on_execute
        self.executed.append((query, params))

    async def fetchone(self) -> tuple | None:
        return self._fetchone_result

    async def fetchall(self) -> list[tuple]:
        return self._fetchall_result


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


def _patch_config(monkeypatch: pytest.MonkeyPatch, user_key: str | None) -> None:
    configurable = {"user_key": user_key} if user_key is not None else {}
    monkeypatch.setattr(store, "get_config", lambda: {"configurable": configurable})


def _telegram_integration(*, user_id: str, chat_id: str) -> UserIntegration:
    return UserIntegration(
        id="integration-1",
        user_id=user_id,
        integration_type="telegram",
        config={"chat_id": chat_id},
    )


def _patch_integration_repository(
    monkeypatch: pytest.MonkeyPatch, integrations: list[UserIntegration]
) -> None:
    """Substitui `PostgresUserIntegrationRepository` por um fake que devolve
    `integrations` de `list_all()` — sem depender de Postgres real."""

    class _FakeRepository:
        def __init__(self, conninfo: str) -> None:
            self.conninfo = conninfo

        async def list_all(self) -> list[UserIntegration]:
            return integrations

    monkeypatch.setattr(store, "PostgresUserIntegrationRepository", _FakeRepository)
    monkeypatch.setenv("POSTGRES_URI", "postgresql://fake")


async def test_resolve_user_id_returns_none_without_user_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_config(monkeypatch, None)
    assert await store.resolve_user_id() is None


async def test_resolve_user_id_strips_web_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_config(monkeypatch, "web:user-abc")

    def _explode(conninfo: str) -> None:
        raise AssertionError("sessão web: não deveria consultar user_integrations")

    monkeypatch.setattr(store, "PostgresUserIntegrationRepository", _explode)

    assert await store.resolve_user_id() == "user-abc"


async def test_resolve_user_id_telegram_linked_returns_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REQ-006 cenário 1 (telegram-channel delta): chat_id com vínculo ativo
    resolve para o `user_id` dono do vínculo."""
    _patch_config(monkeypatch, "telegram:12345")
    _patch_integration_repository(
        monkeypatch, [_telegram_integration(user_id="user-xyz", chat_id="12345")]
    )

    assert await store.resolve_user_id() == "user-xyz"


async def test_resolve_user_id_telegram_unlinked_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REQ-006 cenário 2 (telegram-channel delta): chat_id sem vínculo (ou só
    autorizado pelo fallback legado) não resolve identidade."""
    _patch_config(monkeypatch, "telegram:99999")
    _patch_integration_repository(monkeypatch, [])

    assert await store.resolve_user_id() is None


async def test_resolve_user_id_telegram_ignores_other_chat_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Vínculo de OUTRO chat_id não vaza para uma sessão diferente."""
    _patch_config(monkeypatch, "telegram:99999")
    _patch_integration_repository(
        monkeypatch, [_telegram_integration(user_id="user-xyz", chat_id="12345")]
    )

    assert await store.resolve_user_id() is None


async def test_record_ownership_skips_insert_without_user_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sem `user_id` resolvível, nenhuma linha é inserida (mesmo comportamento
    "zero servidores" adotado por `mcp_tools_middleware` para sessões sem
    `user_id` resolvível)."""
    _patch_config(monkeypatch, None)
    cursor = _FakeCursor()
    _patch_pool(monkeypatch, cursor)

    await store.record_ownership(kind="docx", filename="report.docx")

    assert cursor.executed == []


async def test_record_ownership_inserts_row_for_web_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_config(monkeypatch, "web:user-abc")
    cursor = _FakeCursor()
    _patch_pool(monkeypatch, cursor)

    await store.record_ownership(kind="docx", filename="report.docx")

    assert len(cursor.executed) == 1
    query, params = cursor.executed[0]
    assert "INSERT INTO generated_files" in query
    assert params == ("user-abc", "docx", "report.docx")


async def test_record_ownership_propagates_db_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fail-closed (media-1 acceptance criteria): erro do Postgres propaga —
    quem chama decide que a geração não foi bem-sucedida."""
    _patch_config(monkeypatch, "web:user-abc")
    cursor = _FakeCursor(raise_on_execute=RuntimeError("db down"))
    _patch_pool(monkeypatch, cursor)

    with pytest.raises(RuntimeError, match="db down"):
        await store.record_ownership(kind="image", filename="pic.png")


# --- REQ-002: is_authorized (documents_router / images_router) ---------------

_OWNER = User(id="owner-1", username="owner", password_hash="x", role="user", is_active=True)
_OTHER = User(id="other-1", username="other", password_hash="x", role="user", is_active=True)
_ADMIN = User(id="admin-1", username="admin", password_hash="x", role="admin", is_active=True)


async def test_is_authorized_true_for_owner(monkeypatch: pytest.MonkeyPatch) -> None:
    cursor = _FakeCursor(fetchone_result=("owner-1",))
    _patch_pool(monkeypatch, cursor)

    result = await store.is_authorized(kind="docx", filename="report.docx", user=_OWNER)

    assert result is True
    query, params = cursor.executed[0]
    assert "SELECT" in query
    assert "generated_files" in query
    assert params == ("docx", "report.docx")


async def test_is_authorized_false_for_non_owner(monkeypatch: pytest.MonkeyPatch) -> None:
    cursor = _FakeCursor(fetchone_result=("owner-1",))
    _patch_pool(monkeypatch, cursor)

    result = await store.is_authorized(kind="docx", filename="report.docx", user=_OTHER)

    assert result is False


async def test_is_authorized_true_for_admin_without_querying_db(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Admin faz bypass total (REQ-002) — nem precisa consultar `generated_files`."""

    def _explode() -> None:
        raise AssertionError("get_pool() não deveria ser chamado para admin")

    monkeypatch.setattr(store, "get_pool", _explode)

    result = await store.is_authorized(kind="docx", filename="report.docx", user=_ADMIN)

    assert result is True


async def test_is_authorized_false_when_no_row_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Arquivo em disco sem linha em `generated_files` é inacessível (fail-closed)."""
    cursor = _FakeCursor(fetchone_result=None)
    _patch_pool(monkeypatch, cursor)

    result = await store.is_authorized(kind="docx", filename="orphan.docx", user=_OWNER)

    assert result is False


# --- REQ-003: list_owned_filenames (images_router listing) -------------------


async def test_list_owned_filenames_returns_rows_for_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cursor = _FakeCursor(fetchall_result=[("a.png",), ("b.png",)])
    _patch_pool(monkeypatch, cursor)

    result = await store.list_owned_filenames(kind="image", user_id="owner-1")

    assert result == frozenset({"a.png", "b.png"})
    query, params = cursor.executed[0]
    assert "SELECT" in query
    assert "generated_files" in query
    assert params == ("image", "owner-1")


async def test_list_owned_filenames_empty_for_user_without_files(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cursor = _FakeCursor(fetchall_result=[])
    _patch_pool(monkeypatch, cursor)

    result = await store.list_owned_filenames(kind="image", user_id="owner-1")

    assert result == frozenset()
