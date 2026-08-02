"""Caso de uso: redimir um código de vínculo Telegram (`/start <code>`).

REQ-002/REQ-003 do spec `user-integration-credentials-telegram-account-linking`:
código válido, não-expirado e não-usado vincula o `chat_id` ao `user_id`
dono do código, substituindo qualquer vínculo Telegram anterior desse
usuário, e invalida o código (single-use). Código desconhecido, expirado ou
já redimido levanta o mesmo erro — nenhum dos dois casos revela detalhe
adicional (REQ-002 cenários 2/3), espelhando a convenção de
`GetUserIntegration`/`UserIntegrationAdminDecryptionForbiddenError`.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from src.application.ports.telegram_link_code_repository import (
    TelegramLinkCodeRepositoryPort,
)
from src.application.ports.user_integration_repository import (
    UserIntegrationRepositoryPort,
)
from src.domain.integrations import UserIntegration

_INTEGRATION_TYPE = "telegram"


class TelegramLinkCodeInvalidError(Exception):
    """Código inexistente, expirado ou já redimido — não pode ser usado."""


class RedeemTelegramLinkCode:
    """Redime um `TelegramLinkCode`, vinculando `chat_id` ao `user_id` dono.

    Depende apenas das portas de repositório; não conhece Postgres nem
    qualquer adapter concreto.
    """

    def __init__(
        self,
        *,
        link_code_repository: TelegramLinkCodeRepositoryPort,
        user_integration_repository: UserIntegrationRepositoryPort,
    ) -> None:
        """Recebe as portas de repositório por injeção de dependência."""
        self._link_codes = link_code_repository
        self._user_integrations = user_integration_repository

    async def execute(self, *, code: str, chat_id: str) -> UserIntegration:
        """Redime `code`, vinculando `chat_id` ao `user_id` do código.

        Args:
            code: Código enviado via `/start <code>`.
            chat_id: `chat_id` do Telegram que enviou o comando.

        Returns:
            A `UserIntegration` (`integration_type="telegram"`) resultante,
            criada ou atualizada.

        Raises:
            TelegramLinkCodeInvalidError: código inexistente, expirado ou já
                redimido (mesmo erro para os três casos).
        """
        link_code = await self._link_codes.get(code)
        if link_code is None or link_code.expires_at <= datetime.now(UTC):
            raise TelegramLinkCodeInvalidError(
                "Código de vínculo inválido, expirado ou já utilizado."
            )

        prior_bindings = [
            integration
            for integration in await self._user_integrations.list_by_user(link_code.user_id)
            if integration.integration_type == _INTEGRATION_TYPE
        ]
        integration = UserIntegration(
            id=prior_bindings[0].id if prior_bindings else uuid.uuid4().hex,
            user_id=link_code.user_id,
            integration_type=_INTEGRATION_TYPE,
            config={"chat_id": chat_id},
            created_at=prior_bindings[0].created_at if prior_bindings else datetime.now(UTC),
        )
        await self._user_integrations.save(integration)
        await self._link_codes.delete(code)
        return integration
