"""Testes de `ResolveDeliveryTarget` (scheduled-channel-routines-task-resolve-1).

Cobre:
- unit-1 (REQ-002): whatsapp com vínculo → `whatsapp:<phone>`
- unit-2 (REQ-002): telegram sem vínculo → `DomainError`
- unit-3 (REQ-004): listagem só canais do caller (+ web)
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.application.ports.user_integration_repository import (
    UserIntegrationRepositoryPort,
)
from src.domain.integrations import UserIntegration
from src.domain.shared.errors import DomainError

# ---------------------------------------------------------------------------
# Fake
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


def _integration(
    *,
    id_: str,
    user_id: str,
    integration_type: str,
    config: dict[str, object],
) -> UserIntegration:
    return UserIntegration(
        id=id_,
        user_id=user_id,
        integration_type=integration_type,
        config=config,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


# ===========================================================================
# unit-1 — resolve WhatsApp com vínculo
# ===========================================================================


@pytest.mark.asyncio
async def test_resolve_whatsapp_with_active_link_returns_whatsapp_user_key():
    """unit-1: delivery_channel=whatsapp + vínculo → whatsapp:<phone>."""
    from src.application.use_cases.resolve_delivery_target import ResolveDeliveryTarget

    repo = _FakeRepository()
    await repo.save(
        _integration(
            id_="wa-1",
            user_id="user-a",
            integration_type="whatsapp_business",
            config={"phone_number": "5511999999999"},
        )
    )
    # vínculo de outro usuário NÃO deve vazar
    await repo.save(
        _integration(
            id_="wa-other",
            user_id="user-b",
            integration_type="whatsapp_business",
            config={"phone_number": "5511888888888"},
        )
    )

    result = await ResolveDeliveryTarget(repository=repo).resolve(
        user_id="user-a",
        delivery_channel="whatsapp",
    )

    assert result == "whatsapp:5511999999999"


# ===========================================================================
# unit-2 — Telegram sem vínculo
# ===========================================================================


@pytest.mark.asyncio
async def test_resolve_telegram_without_link_raises_domain_error():
    """unit-2: telegram sem integração → DomainError; não inventa user_key."""
    from src.application.use_cases.resolve_delivery_target import ResolveDeliveryTarget

    repo = _FakeRepository()
    await repo.save(
        _integration(
            id_="wa-1",
            user_id="user-a",
            integration_type="whatsapp_business",
            config={"phone_number": "5511999999999"},
        )
    )

    with pytest.raises(DomainError, match="telegram"):
        await ResolveDeliveryTarget(repository=repo).resolve(
            user_id="user-a",
            delivery_channel="telegram",
        )


@pytest.mark.asyncio
async def test_resolve_rejects_arbitrary_third_party_user_key_as_channel():
    """REQ-003: entrada é só o canal — identificadores crus não são aceitos."""
    from src.application.use_cases.resolve_delivery_target import ResolveDeliveryTarget

    repo = _FakeRepository()

    with pytest.raises(DomainError):
        await ResolveDeliveryTarget(repository=repo).resolve(
            user_id="user-a",
            delivery_channel="whatsapp:5511888888888",
        )


# ===========================================================================
# unit-3 — list_delivery_channels
# ===========================================================================


@pytest.mark.asyncio
async def test_list_delivery_channels_includes_web_and_only_caller_links():
    """unit-3: só Telegram vinculado → web + telegram; sem whatsapp."""
    from src.application.use_cases.resolve_delivery_target import ResolveDeliveryTarget

    repo = _FakeRepository()
    await repo.save(
        _integration(
            id_="tg-1",
            user_id="user-a",
            integration_type="telegram",
            config={"chat_id": "42"},
        )
    )
    await repo.save(
        _integration(
            id_="wa-other",
            user_id="user-b",
            integration_type="whatsapp_business",
            config={"phone_number": "5511888888888"},
        )
    )

    channels = await ResolveDeliveryTarget(repository=repo).list_channels(
        user_id="user-a",
    )

    assert channels == ["web", "telegram"]
