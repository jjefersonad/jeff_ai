"""Caso de uso: buscar uma conta de email por id (REQ-002 email-account-management)."""
from __future__ import annotations

from src.application.ports.email_account_repository import (
    EmailAccountRepositoryPort,
)
from src.domain.email import EmailAccount


class GetEmailAccount:
    """Busca uma conta própria; `None` se miss ou cross-user (sem vazar existência)."""

    def __init__(self, *, repository: EmailAccountRepositoryPort) -> None:
        """Recebe a porta de repositório por injeção."""
        self._repository = repository

    async def execute(self, *, user_id: str, account_id: str) -> EmailAccount | None:
        """Retorna a conta se pertencer a `user_id`, senão `None`."""
        return await self._repository.get(user_id, account_id)
