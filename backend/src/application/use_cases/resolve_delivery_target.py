"""Resolução de destino de entrega para tarefas agendadas.

`delivery_channel` ∈ {web, telegram, whatsapp} → `delivery_user_key`
(`web:<user_id>` / `telegram:<chat_id>` / `whatsapp:<phone>`), usando só
vínculos do próprio `user_id` em `user_integrations` (Decision 1–2 /
REQ-002–004 de `scheduled-delivery-targeting`).

Nunca aceita `user_key` arbitrário como entrada — só o nome do canal.
"""
from __future__ import annotations

from src.application.ports.user_integration_repository import (
    UserIntegrationRepositoryPort,
)
from src.domain.integrations import UserIntegration
from src.domain.shared.errors import DomainError

_ALLOWED_CHANNELS = frozenset({"web", "telegram", "whatsapp"})
_TELEGRAM_INTEGRATION_TYPE = "telegram"
_WHATSAPP_INTEGRATION_TYPE = "whatsapp_business"


class ResolveDeliveryTarget:
    """Resolve e lista canais de entrega a partir dos vínculos do caller."""

    def __init__(self, *, repository: UserIntegrationRepositoryPort) -> None:
        self._repository = repository

    async def resolve(
        self,
        *,
        user_id: str,
        delivery_channel: str | None,
    ) -> str | None:
        """Converte `delivery_channel` em `delivery_user_key` do próprio user.

        Args:
            user_id: UUID canônico do usuário autenticado.
            delivery_channel: `web` / `telegram` / `whatsapp`, ou `None`
                (omite destino explícito — fallback owner no domínio).

        Returns:
            `delivery_user_key` resolvido, ou `None` quando o canal é omitido.

        Raises:
            DomainError: canal inválido, ou vínculo telegram/whatsapp ausente.
        """
        if delivery_channel is None:
            return None

        channel = delivery_channel.strip().lower()
        if channel not in _ALLOWED_CHANNELS:
            raise DomainError(
                "delivery_channel inválido: "
                f"{delivery_channel!r}; use web, telegram ou whatsapp"
            )

        if channel == "web":
            return f"web:{user_id}"

        integrations = await self._repository.list_by_user(user_id)

        if channel == "telegram":
            chat_id = _first_config_str(
                integrations,
                integration_type=_TELEGRAM_INTEGRATION_TYPE,
                config_key="chat_id",
            )
            if chat_id is None:
                raise DomainError(
                    "canal telegram sem vínculo ativo em user_integrations "
                    f"para user_id={user_id!r}"
                )
            return f"telegram:{chat_id}"

        phone = _first_config_str(
            integrations,
            integration_type=_WHATSAPP_INTEGRATION_TYPE,
            config_key="phone_number",
        )
        if phone is None:
            raise DomainError(
                "canal whatsapp sem vínculo ativo em user_integrations "
                f"para user_id={user_id!r}"
            )
        return f"whatsapp:{phone}"

    async def list_channels(self, *, user_id: str) -> list[str]:
        """Canais disponíveis ao caller: sempre `web` + vínculos ativos.

        Ordem estável: web, telegram (se houver), whatsapp (se houver).
        Só inspeciona `list_by_user(user_id)` — nunca vaza vínculos alheios.
        """
        integrations = await self._repository.list_by_user(user_id)
        channels = ["web"]
        if _first_config_str(
            integrations,
            integration_type=_TELEGRAM_INTEGRATION_TYPE,
            config_key="chat_id",
        ) is not None:
            channels.append("telegram")
        if _first_config_str(
            integrations,
            integration_type=_WHATSAPP_INTEGRATION_TYPE,
            config_key="phone_number",
        ) is not None:
            channels.append("whatsapp")
        return channels


def _first_config_str(
    integrations: list[UserIntegration],
    *,
    integration_type: str,
    config_key: str,
) -> str | None:
    for integration in integrations:
        if integration.integration_type != integration_type:
            continue
        value = integration.config.get(config_key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None
