"""Testes dos use cases de `user_integrations` (task `user-integration-credentials-task-store-3`).

Puro: usa fake do `UserIntegrationRepositoryPort`, mesmo padrão de
`test_list_and_cancel_scheduled_tasks.py`. Cobre os 3 unit-tests linkados à
task no OpenSddRag:

- unit-1 (REQ-001): `GetUserIntegration` não revela a existência de uma
  entrada de outro usuário para um chamador não-admin.
- unit-2 (REQ-004): `ListUserIntegrations` para `role=admin` devolve metadados
  de todos os usuários, sem `config` decifrado de quem não é o chamador.
- unit-3 (REQ-004): admin não consegue decifrar o `config` de outro usuário
  via `GetUserIntegration` — recebe um erro explícito, distinto de "não
  encontrado".
"""
from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

import pytest

from src.application.ports.user_integration_repository import (
    UserIntegrationRepositoryPort,
)
from src.application.use_cases.delete_user_integration import DeleteUserIntegration
from src.application.use_cases.get_user_integration import (
    GetUserIntegration,
    UserIntegrationAdminDecryptionForbiddenError,
)
from src.application.use_cases.list_user_integrations import ListUserIntegrations
from src.application.use_cases.save_user_integration import SaveUserIntegration
from src.domain.integrations import UserIntegration

# ---------------------------------------------------------------------------
# Fake local (reaproveita o padrão de test_list_and_cancel_scheduled_tasks.py)
# ---------------------------------------------------------------------------


class _FakeRepository(UserIntegrationRepositoryPort):
    def __init__(self) -> None:
        self._store: dict[str, UserIntegration] = {}

    async def save(self, integration: UserIntegration) -> None:
        self._store[integration.id] = integration

    async def get(self, integration_id: str) -> UserIntegration | None:
        return self._store.get(integration_id)

    async def list_by_user(self, user_id: str) -> list[UserIntegration]:
        return [i for i in self._store.values() if i.user_id == user_id]

    async def list_all(self) -> list[UserIntegration]:
        return list(self._store.values())

    async def delete(self, integration_id: str) -> None:
        self._store.pop(integration_id, None)


def _make_integration(
    *, id_: str, user_id: str, config: dict[str, object] | None = None
) -> UserIntegration:
    return UserIntegration(
        id=id_,
        user_id=user_id,
        integration_type="telegram",
        config=config or {"chat_id": "123"},
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


# ===========================================================================
# GetUserIntegration — unit-1 (REQ-001) / unit-3 (REQ-004)
# ===========================================================================


@pytest.mark.asyncio
async def test_get_returns_own_entry_decrypted_for_owner():
    repo = _FakeRepository()
    await repo.save(_make_integration(id_="i-1", user_id="user-a"))

    use_case = GetUserIntegration(repository=repo)
    result = await use_case.execute(
        integration_id="i-1", caller_user_id="user-a", is_admin=False
    )

    assert result is not None
    assert result.config == {"chat_id": "123"}


@pytest.mark.asyncio
async def test_get_for_non_admin_non_owner_returns_none_without_revealing_existence():
    """unit-1: usuário A não-admin pedindo a entrada de B recebe None (não erro)."""
    repo = _FakeRepository()
    await repo.save(_make_integration(id_="i-1", user_id="user-b"))

    use_case = GetUserIntegration(repository=repo)
    result = await use_case.execute(
        integration_id="i-1", caller_user_id="user-a", is_admin=False
    )

    assert result is None


@pytest.mark.asyncio
async def test_get_nonexistent_entry_returns_none_same_as_unauthorized():
    """Mesma resposta para "não existe" e "existe mas não é meu" (REQ-001)."""
    repo = _FakeRepository()

    use_case = GetUserIntegration(repository=repo)
    result = await use_case.execute(
        integration_id="does-not-exist", caller_user_id="user-a", is_admin=False
    )

    assert result is None


@pytest.mark.asyncio
async def test_get_for_admin_non_owner_raises_instead_of_decrypting():
    """unit-3: admin pedindo entrada de outro usuário recebe erro explícito."""
    repo = _FakeRepository()
    await repo.save(_make_integration(id_="i-1", user_id="user-b"))

    use_case = GetUserIntegration(repository=repo)
    with pytest.raises(UserIntegrationAdminDecryptionForbiddenError) as exc_info:
        await use_case.execute(
            integration_id="i-1", caller_user_id="admin-x", is_admin=True
        )

    assert "i-1" in str(exc_info.value)


@pytest.mark.asyncio
async def test_get_for_admin_owner_returns_decrypted():
    """Admin lendo a PRÓPRIA entrada recebe o config decifrado normalmente."""
    repo = _FakeRepository()
    await repo.save(_make_integration(id_="i-1", user_id="admin-x"))

    use_case = GetUserIntegration(repository=repo)
    result = await use_case.execute(
        integration_id="i-1", caller_user_id="admin-x", is_admin=True
    )

    assert result is not None
    assert result.config == {"chat_id": "123"}


# ===========================================================================
# ListUserIntegrations — unit-2 (REQ-004)
# ===========================================================================


@pytest.mark.asyncio
async def test_list_for_non_admin_returns_only_own_entries_decrypted():
    repo = _FakeRepository()
    await repo.save(_make_integration(id_="i-a", user_id="user-a"))
    await repo.save(_make_integration(id_="i-b", user_id="user-b"))

    use_case = ListUserIntegrations(repository=repo)
    result = await use_case.execute(caller_user_id="user-a", is_admin=False)

    assert [s.id for s in result] == ["i-a"]
    assert result[0].config == {"chat_id": "123"}


@pytest.mark.asyncio
async def test_list_for_admin_includes_all_users_without_others_config():
    """unit-2: admin vê metadados de todos, mas config só da própria entrada."""
    repo = _FakeRepository()
    await repo.save(_make_integration(id_="i-a", user_id="user-a"))
    await repo.save(_make_integration(id_="i-b", user_id="user-b"))
    await repo.save(_make_integration(id_="i-admin", user_id="admin-x"))

    use_case = ListUserIntegrations(repository=repo)
    result = await use_case.execute(caller_user_id="admin-x", is_admin=True)

    by_id = {s.id: s for s in result}
    assert set(by_id) == {"i-a", "i-b", "i-admin"}
    # Metadados sempre presentes, mesmo para entradas de outros usuários.
    assert by_id["i-a"].user_id == "user-a"
    assert by_id["i-a"].integration_type == "telegram"
    # config decifrado NUNCA aparece para entradas que não são do admin.
    assert by_id["i-a"].config is None
    assert by_id["i-b"].config is None
    # A própria entrada do admin continua com config decifrado.
    assert by_id["i-admin"].config == {"chat_id": "123"}


@pytest.mark.asyncio
async def test_list_returns_empty_list_when_caller_has_no_entries():
    repo = _FakeRepository()
    await repo.save(_make_integration(id_="i-other", user_id="someone-else"))

    use_case = ListUserIntegrations(repository=repo)
    result = await use_case.execute(caller_user_id="user-a", is_admin=False)

    assert result == []


# ===========================================================================
# SaveUserIntegration — REQ-001 cenário 2 (update)
# ===========================================================================


@pytest.mark.asyncio
async def test_save_creates_new_entry_for_owner():
    repo = _FakeRepository()
    integration = _make_integration(id_="i-new", user_id="user-a")

    use_case = SaveUserIntegration(repository=repo)
    result = await use_case.execute(
        integration=integration, caller_user_id="user-a", is_admin=False
    )

    assert result is not None
    assert await repo.get("i-new") is not None


@pytest.mark.asyncio
async def test_save_updating_another_users_entry_is_rejected_without_error():
    """Não-dono não-admin tentando sobrescrever a entrada de outro: rejeitado, sem revelar."""
    repo = _FakeRepository()
    await repo.save(_make_integration(id_="i-1", user_id="user-b", config={"chat_id": "orig"}))
    tampered = _make_integration(id_="i-1", user_id="user-b", config={"chat_id": "hacked"})

    use_case = SaveUserIntegration(repository=repo)
    result = await use_case.execute(
        integration=tampered, caller_user_id="user-a", is_admin=False
    )

    assert result is None
    unchanged = await repo.get("i-1")
    assert unchanged is not None
    assert unchanged.config == {"chat_id": "orig"}


@pytest.mark.asyncio
async def test_save_allows_admin_to_update_another_users_entry():
    repo = _FakeRepository()
    await repo.save(_make_integration(id_="i-1", user_id="user-b", config={"chat_id": "orig"}))
    updated = _make_integration(id_="i-1", user_id="user-b", config={"chat_id": "new"})

    use_case = SaveUserIntegration(repository=repo)
    result = await use_case.execute(
        integration=updated, caller_user_id="admin-x", is_admin=True
    )

    assert result is not None
    saved = await repo.get("i-1")
    assert saved is not None
    assert saved.config == {"chat_id": "new"}


# ===========================================================================
# DeleteUserIntegration — REQ-001 cenário 2 (delete)
# ===========================================================================


@pytest.mark.asyncio
async def test_delete_removes_own_entry_for_owner():
    repo = _FakeRepository()
    await repo.save(_make_integration(id_="i-1", user_id="user-a"))

    use_case = DeleteUserIntegration(repository=repo)
    await use_case.execute(
        integration_id="i-1", caller_user_id="user-a", is_admin=False
    )

    assert await repo.get("i-1") is None


@pytest.mark.asyncio
async def test_delete_by_non_admin_non_owner_is_silent_noop():
    repo = _FakeRepository()
    await repo.save(_make_integration(id_="i-1", user_id="user-b"))

    use_case = DeleteUserIntegration(repository=repo)
    await use_case.execute(
        integration_id="i-1", caller_user_id="user-a", is_admin=False
    )

    # Entrada de outro usuário permanece intacta — rejeição silenciosa.
    assert await repo.get("i-1") is not None


@pytest.mark.asyncio
async def test_delete_by_admin_removes_another_users_entry():
    repo = _FakeRepository()
    await repo.save(_make_integration(id_="i-1", user_id="user-b"))

    use_case = DeleteUserIntegration(repository=repo)
    await use_case.execute(
        integration_id="i-1", caller_user_id="admin-x", is_admin=True
    )

    assert await repo.get("i-1") is None


@pytest.mark.asyncio
async def test_delete_nonexistent_entry_is_tolerated_noop():
    repo = _FakeRepository()

    use_case = DeleteUserIntegration(repository=repo)
    # NÃO deve levantar.
    await use_case.execute(
        integration_id="does-not-exist", caller_user_id="user-a", is_admin=False
    )


# ===========================================================================
# Guard estático contra framework concreto (mesma convenção das outras suites)
# ===========================================================================


@pytest.mark.parametrize(
    "filename",
    [
        "save_user_integration.py",
        "get_user_integration.py",
        "list_user_integrations.py",
        "delete_user_integration.py",
    ],
)
def test_use_case_modules_do_not_import_framework(filename: str):
    src = (
        Path(__file__).parent.parent / "src" / "application" / "use_cases" / filename
    ).read_text()
    no_strings = re.sub(r'""".*?""""', "", src, flags=re.DOTALL)
    no_strings = re.sub(r"'''.*?'''", "", no_strings, flags=re.DOTALL)
    for forbidden in ("psycopg", "apscheduler", "langgraph", "fastapi"):
        assert not re.search(
            rf"^\s*(import|from)\s+{forbidden}\b", no_strings, flags=re.MULTILINE
        ), f"{filename} não pode importar {forbidden!r}"
