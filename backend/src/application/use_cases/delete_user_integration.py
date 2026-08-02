"""Caso de uso: remover uma credencial de integração de usuário.

Cobre REQ-001 cenário 2 do spec `user-integration-credentials-store`: um
não-dono não-admin tentando remover a entrada de outro usuário é rejeitado
silenciosamente, sem revelar se a entrada existe — mesma resposta do caso
"id inexistente" (no-op tolerante).
"""
from __future__ import annotations

from src.application.ports.user_integration_repository import (
    UserIntegrationRepositoryPort,
)


class DeleteUserIntegration:
    """Remove uma `UserIntegration`, escopada ao dono (REQ-001).

    Depende apenas da porta de repositório; não conhece Postgres nem
    qualquer adapter concreto.
    """

    def __init__(self, *, repository: UserIntegrationRepositoryPort) -> None:
        """Recebe a porta de repositório por injeção de dependência."""
        self._repository = repository

    async def execute(
        self,
        *,
        integration_id: str,
        caller_user_id: str,
        is_admin: bool,
    ) -> None:
        """Remove a entrada se o chamador for o dono ou admin.

        Args:
            integration_id: Identificador da entrada a remover.
            caller_user_id: `user_id` do chamador autenticado.
            is_admin: True se o chamador tem `role=admin`.

        No-op tolerante (não levanta exceção) tanto para `integration_id`
        inexistente quanto para não-dono não-admin — REQ-001 exige não
        revelar existência, então as duas situações são indistinguíveis
        pelo caller.
        """
        integration = await self._repository.get(integration_id)
        if integration is None:
            return
        if integration.user_id != caller_user_id and not is_admin:
            return
        await self._repository.delete(integration_id)
