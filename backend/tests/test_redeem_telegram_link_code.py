"""Testes do use case `RedeemTelegramLinkCode`
(task `user-integration-credentials-task-linking-1`).

Puro: usa fakes de `TelegramLinkCodeRepositoryPort` e
`UserIntegrationRepositoryPort`, mesmo padrão de
`test_user_integration_use_cases.py`. Cobre os 3 unit-tests linkados à task
no OpenSddRag:

- unit-1 (REQ-002 cenário 1): código válido vincula o chat_id ao user_id
  dono do código e invalida o código.
- unit-2 (REQ-002 cenários 2/3): código expirado, inexistente ou já usado é
  rejeitado sem criar/alterar `user_integrations`.
- unit-3 (REQ-003): redimir um segundo código válido substitui o vínculo
  anterior do mesmo usuário — o chat_id antigo deixa de resolver para ele.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from src.application.ports.telegram_link_code_repository import (
    TelegramLinkCodeRepositoryPort,
)
from src.application.ports.user_integration_repository import (
    UserIntegrationRepositoryPort,
)
from src.application.use_cases.redeem_telegram_link_code import (
    RedeemTelegramLinkCode,
    TelegramLinkCodeInvalidError,
)
from src.domain.integrations import TelegramLinkCode, UserIntegration


class _FakeLinkCodeRepository(TelegramLinkCodeRepositoryPort):
    def __init__(self) -> None:
        self._store: dict[str, TelegramLinkCode] = {}

    async def save(self, link_code: TelegramLinkCode) -> None:
        self._store[link_code.code] = link_code

    async def get(self, code: str) -> TelegramLinkCode | None:
        return self._store.get(code)

    async def delete(self, code: str) -> None:
        self._store.pop(code, None)


class _FakeUserIntegrationRepository(UserIntegrationRepositoryPort):
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


def _valid_code(*, code: str = "ABC123", user_id: str = "user-a") -> TelegramLinkCode:
    return TelegramLinkCode(
        code=code, user_id=user_id, expires_at=datetime.now(UTC) + timedelta(minutes=10)
    )


def _expired_code(*, code: str = "OLD999", user_id: str = "user-a") -> TelegramLinkCode:
    return TelegramLinkCode(
        code=code, user_id=user_id, expires_at=datetime.now(UTC) - timedelta(minutes=1)
    )


@pytest.fixture
def link_codes() -> _FakeLinkCodeRepository:
    return _FakeLinkCodeRepository()


@pytest.fixture
def user_integrations() -> _FakeUserIntegrationRepository:
    return _FakeUserIntegrationRepository()


# ===========================================================================
# unit-1 (REQ-002 cenário 1): código válido vincula o chat_id
# ===========================================================================


@pytest.mark.asyncio
async def test_valid_code_binds_chat_id_to_owning_user_and_invalidates_code(
    link_codes: _FakeLinkCodeRepository, user_integrations: _FakeUserIntegrationRepository
) -> None:
    await link_codes.save(_valid_code(code="ABC123", user_id="user-a"))

    use_case = RedeemTelegramLinkCode(
        link_code_repository=link_codes, user_integration_repository=user_integrations
    )
    result = await use_case.execute(code="ABC123", chat_id="chat-1")

    assert result.user_id == "user-a"
    assert result.integration_type == "telegram"
    assert result.config == {"chat_id": "chat-1"}
    bound = await user_integrations.list_by_user("user-a")
    assert len(bound) == 1
    assert bound[0].config == {"chat_id": "chat-1"}
    assert await link_codes.get("ABC123") is None


# ===========================================================================
# unit-2 (REQ-002 cenários 2/3): código expirado/inexistente/reusado rejeitado
# ===========================================================================


@pytest.mark.asyncio
async def test_unknown_code_is_rejected_without_creating_binding(
    link_codes: _FakeLinkCodeRepository, user_integrations: _FakeUserIntegrationRepository
) -> None:
    use_case = RedeemTelegramLinkCode(
        link_code_repository=link_codes, user_integration_repository=user_integrations
    )

    with pytest.raises(TelegramLinkCodeInvalidError):
        await use_case.execute(code="DOES-NOT-EXIST", chat_id="chat-1")

    assert await user_integrations.list_all() == []


@pytest.mark.asyncio
async def test_expired_code_is_rejected_without_creating_binding(
    link_codes: _FakeLinkCodeRepository, user_integrations: _FakeUserIntegrationRepository
) -> None:
    await link_codes.save(_expired_code(code="OLD999", user_id="user-a"))

    use_case = RedeemTelegramLinkCode(
        link_code_repository=link_codes, user_integration_repository=user_integrations
    )

    with pytest.raises(TelegramLinkCodeInvalidError):
        await use_case.execute(code="OLD999", chat_id="chat-1")

    assert await user_integrations.list_all() == []


@pytest.mark.asyncio
async def test_already_redeemed_code_cannot_be_redeemed_twice(
    link_codes: _FakeLinkCodeRepository, user_integrations: _FakeUserIntegrationRepository
) -> None:
    await link_codes.save(_valid_code(code="ABC123", user_id="user-a"))
    use_case = RedeemTelegramLinkCode(
        link_code_repository=link_codes, user_integration_repository=user_integrations
    )
    await use_case.execute(code="ABC123", chat_id="chat-1")

    with pytest.raises(TelegramLinkCodeInvalidError):
        await use_case.execute(code="ABC123", chat_id="chat-2")

    bound = await user_integrations.list_by_user("user-a")
    assert len(bound) == 1
    assert bound[0].config == {"chat_id": "chat-1"}


# ===========================================================================
# unit-3 (REQ-003): re-link substitui o vínculo anterior
# ===========================================================================


@pytest.mark.asyncio
async def test_relinking_replaces_prior_binding_old_chat_id_no_longer_bound(
    link_codes: _FakeLinkCodeRepository, user_integrations: _FakeUserIntegrationRepository
) -> None:
    await link_codes.save(_valid_code(code="FIRST1", user_id="user-a"))
    use_case = RedeemTelegramLinkCode(
        link_code_repository=link_codes, user_integration_repository=user_integrations
    )
    await use_case.execute(code="FIRST1", chat_id="old-chat")

    await link_codes.save(_valid_code(code="SECOND2", user_id="user-a"))
    await use_case.execute(code="SECOND2", chat_id="new-chat")

    bound = await user_integrations.list_by_user("user-a")
    assert len(bound) == 1
    assert bound[0].config == {"chat_id": "new-chat"}
