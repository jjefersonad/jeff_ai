"""Caso de uso: buscar uma credencial de integração de usuário por id.

Cobre REQ-001 cenário 2 e REQ-004 do spec `user-integration-credentials-store`:
- Não-dono não-admin recebe `None` (mesma resposta de "não existe" — REQ-001
  exige não revelar existência, diferente de `CancelScheduledTask`, que pode
  revelar).
- Admin não-dono recebe `UserIntegrationAdminDecryptionForbiddenError`
  explícito em vez do `config` decifrado (REQ-004) — aqui a existência já é
  visível via `ListUserIntegrations`, então o erro explícito é seguro.
"""
from __future__ import annotations

from src.application.ports.user_integration_repository import (
    UserIntegrationRepositoryPort,
)
from src.domain.integrations import UserIntegration


class UserIntegrationAdminDecryptionForbiddenError(Exception):
    """Admin tentou obter o `config` decifrado de uma entrada de outro usuário.

    Tipo próprio (REQ-004) — distinto de "não encontrado" (`None`), porque
    para um admin a existência da entrada já não é segredo (aparece em
    `ListUserIntegrations`); o que é proibido é decifrar o `config`.
    """

    def __init__(self, *, integration_id: str) -> None:
        """Captura o id para uma mensagem acionável."""
        self.integration_id = integration_id
        super().__init__(
            f"Admin não pode decifrar o config da entrada {integration_id!r}: "
            "pertence a outro usuário (REQ-004)."
        )


class GetUserIntegration:
    """Busca uma `UserIntegration` por id, escopada ao dono (REQ-001/REQ-004).

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
    ) -> UserIntegration | None:
        """Retorna a entrada decifrada se o chamador for o dono.

        Args:
            integration_id: Identificador da entrada.
            caller_user_id: `user_id` do chamador autenticado.
            is_admin: True se o chamador tem `role=admin`.

        Returns:
            A `UserIntegration` decifrada quando `caller_user_id` é o dono,
            ou quando a entrada não existe (mesma resposta, REQ-001).

        Raises:
            UserIntegrationAdminDecryptionForbiddenError: Quando o chamador
                é admin mas não é o dono — a entrada existe, mas seu
                `config` decifrado não pode ser exposto (REQ-004).
        """
        integration = await self._repository.get(integration_id)
        if integration is None:
            return None
        if integration.user_id == caller_user_id:
            return integration
        if is_admin:
            raise UserIntegrationAdminDecryptionForbiddenError(
                integration_id=integration_id
            )
        # Não-dono não-admin: mesma resposta do "não existe" (REQ-001).
        return None
