"""Caso de uso: remover uma conta de email (REQ-004 email-account-management).

Remove a `EmailAccount` e sua `UserIntegration` (`integration_type="imap"`)
ligada. Não referencia nenhum repositório de `emails`/`email_attachments` —
por construção não pode apagar mensagens já sincronizadas dessa conta
(retidas até uma remoção explícita separada, fora de escopo deste caso de
uso).
"""
from __future__ import annotations

from src.application.ports.email_account_repository import (
    EmailAccountRepositoryPort,
)
from src.application.ports.user_integration_repository import (
    UserIntegrationRepositoryPort,
)


class DeleteEmailAccount:
    """Remove a conta própria e a credencial ligada a ela."""

    def __init__(
        self,
        *,
        repository: EmailAccountRepositoryPort,
        integration_repository: UserIntegrationRepositoryPort,
    ) -> None:
        """Recebe as duas portas de repositório por injeção de dependência."""
        self._repository = repository
        self._integration_repository = integration_repository

    async def execute(self, *, user_id: str, account_id: str) -> bool:
        """Remove a conta e sua credencial; `False` se miss ou cross-user."""
        account = await self._repository.get(user_id, account_id)
        if account is None:
            return False
        deleted = await self._repository.delete(user_id, account_id)
        if deleted:
            await self._integration_repository.delete(account.user_integration_id)
        return deleted
