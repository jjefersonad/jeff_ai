"""Caso de uso: redimir um código de vínculo WhatsApp.

whatsapp-channel REQ-001: código válido, não-expirado e não-usado vincula o
`phone_number` remetente ao `user_id` dono do código, e invalida o código
(single-use). Código desconhecido ou expirado levanta o mesmo erro — o
handler do webhook (`whatsapp-evolution-channel-task-linking-3`) trata isso
como "não é um código de vínculo", seguindo para o fluxo normal de
autorização (`task-channel-3`) em vez de propagar a exceção.

Diferente de `RedeemTelegramLinkCode`, não substitui um vínculo `whatsapp_
business` anterior do mesmo usuário — REQ-001 não exige isso (nenhum cenário
do spec cobre re-vínculo), então cada redenção cria uma entrada nova.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from src.application.ports.user_integration_repository import (
    UserIntegrationRepositoryPort,
)
from src.application.ports.whatsapp_link_code_repository import (
    WhatsAppLinkCodeRepositoryPort,
)
from src.domain.integrations import UserIntegration

_INTEGRATION_TYPE = "whatsapp_business"


class WhatsAppLinkCodeInvalidError(Exception):
    """Código inexistente, expirado ou já redimido — não pode ser usado."""


class RedeemWhatsAppLinkCode:
    """Redime um `WhatsAppLinkCode`, vinculando `phone_number` ao `user_id` dono.

    Depende apenas das portas de repositório; não conhece Postgres nem
    qualquer adapter concreto.
    """

    def __init__(
        self,
        *,
        link_code_repository: WhatsAppLinkCodeRepositoryPort,
        user_integration_repository: UserIntegrationRepositoryPort,
    ) -> None:
        """Recebe as portas de repositório por injeção de dependência."""
        self._link_codes = link_code_repository
        self._user_integrations = user_integration_repository

    async def execute(self, *, code: str, phone_number: str) -> UserIntegration:
        """Redime `code`, vinculando `phone_number` ao `user_id` do código.

        Args:
            code: Texto recebido pelo número central, comparado a um código
                de vínculo pendente.
            phone_number: Número de telefone remetente da mensagem.

        Returns:
            A `UserIntegration` (`integration_type="whatsapp_business"`) criada.

        Raises:
            WhatsAppLinkCodeInvalidError: código inexistente ou expirado.
        """
        link_code = await self._link_codes.get(code)
        if link_code is None or link_code.expires_at <= datetime.now(UTC):
            raise WhatsAppLinkCodeInvalidError(
                "Código de vínculo inválido, expirado ou já utilizado."
            )

        integration = UserIntegration(
            id=uuid.uuid4().hex,
            user_id=link_code.user_id,
            integration_type=_INTEGRATION_TYPE,
            config={"phone_number": phone_number},
        )
        await self._user_integrations.save(integration)
        await self._link_codes.delete(code)
        return integration
