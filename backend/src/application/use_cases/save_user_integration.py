"""Caso de uso: criar ou atualizar uma credencial de integração de usuário.

Cobre REQ-001 cenário 2 do spec `user-integration-credentials-store`: um
não-dono não-admin tentando sobrescrever a entrada de outro usuário é
rejeitado sem revelar se a entrada existe (mesma resposta de "id livre para
criar" — o caller decide como comunicar isso).
"""
from __future__ import annotations

from src.application.ports.user_integration_repository import (
    UserIntegrationRepositoryPort,
)
from src.domain.integrations import UserIntegration


class SaveUserIntegration:
    """Cria ou atualiza uma `UserIntegration`, escopada ao dono (REQ-001).

    Depende apenas da porta de repositório; não conhece Postgres nem
    qualquer adapter concreto.
    """

    def __init__(self, *, repository: UserIntegrationRepositoryPort) -> None:
        """Recebe a porta de repositório por injeção de dependência."""
        self._repository = repository

    async def execute(
        self,
        *,
        integration: UserIntegration,
        caller_user_id: str,
        is_admin: bool,
    ) -> UserIntegration | None:
        """Persista `integration` se o `id` for novo ou já pertencer ao chamador.

        Args:
            integration: Entidade já validada pelo schema de
                `integration_type` (fronteira do use case, chamador
                garante isso antes de invocar).
            caller_user_id: `user_id` do chamador autenticado.
            is_admin: True se o chamador tem `role=admin`.

        Returns:
            `integration` persistida, ou `None` quando o `id` já pertence a
            outro usuário e o chamador não é dono nem admin — rejeição sem
            revelar a existência (REQ-001).
        """
        existing = await self._repository.get(integration.id)
        if (
            existing is not None
            and existing.user_id != caller_user_id
            and not is_admin
        ):
            return None
        await self._repository.save(integration)
        return integration
