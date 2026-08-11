"""Caso de uso: editar metadata de uma conta de email (REQ-002 email-account-management).

Edita apenas `display_name`/`is_active` — as credenciais IMAP/SMTP não são
editáveis por aqui (re-validação/re-cifra ficam fora de escopo deste caso de
uso; o usuário reconecta a conta para trocar credenciais).
"""
from __future__ import annotations

from datetime import UTC, datetime

from src.application.ports.email_account_repository import (
    EmailAccountRepositoryPort,
)
from src.domain.email import EmailAccount


class UpdateEmailAccount:
    """Atualiza `display_name`/`is_active` de uma conta própria."""

    def __init__(self, *, repository: EmailAccountRepositoryPort) -> None:
        """Recebe a porta de repositório por injeção."""
        self._repository = repository

    async def execute(
        self,
        *,
        user_id: str,
        account_id: str,
        display_name: str | None = None,
        is_active: bool | None = None,
    ) -> EmailAccount | None:
        """Aplica as mudanças informadas; `None` se miss ou cross-user."""
        existing = await self._repository.get(user_id, account_id)
        if existing is None:
            return None
        if display_name is not None:
            existing.display_name = display_name
        if is_active is not None:
            existing.is_active = is_active
        existing.updated_at = datetime.now(UTC)
        return await self._repository.update(existing)
