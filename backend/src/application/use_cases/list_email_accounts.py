"""Caso de uso: listar contas de email do usuário (REQ-002 email-account-management)."""
from __future__ import annotations

from src.application.ports.email_account_repository import (
    EmailAccountRepositoryPort,
)
from src.domain.email import EmailAccount


class ListEmailAccounts:
    """Lista as contas de email escopadas ao `user_id` chamador."""

    def __init__(self, *, repository: EmailAccountRepositoryPort) -> None:
        """Recebe a porta de repositório por injeção."""
        self._repository = repository

    async def execute(self, *, user_id: str) -> list[EmailAccount]:
        """Retorna as contas do `user_id`, nunca as de outro usuário."""
        return await self._repository.list_by_user(user_id)
