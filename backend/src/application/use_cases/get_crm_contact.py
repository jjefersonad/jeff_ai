"""Caso de uso: obter contato CRM (REQ-002 / REQ-005 crm-contacts)."""
from __future__ import annotations

from src.application.ports.crm_repository import CrmRepositoryPort
from src.domain.crm import Contact


class GetCrmContact:
    """Obtém um contato do usuário autenticado (miss → None)."""

    def __init__(self, *, repository: CrmRepositoryPort) -> None:
        """Recebe a porta de repositório por injeção."""
        self._repository = repository

    async def execute(self, *, user_id: str, contact_id: str) -> Contact | None:
        """Retorna o contato próprio ou ``None`` (inclui cross-user)."""
        return await self._repository.get_contact(user_id, contact_id)
