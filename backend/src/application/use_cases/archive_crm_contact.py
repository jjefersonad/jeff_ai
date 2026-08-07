"""Caso de uso: arquivar contato CRM (REQ-004 / REQ-005 crm-contacts)."""
from __future__ import annotations

from src.application.ports.crm_repository import CrmRepositoryPort
from src.domain.crm import Contact


class ArchiveCrmContact:
    """Soft-archive de um contato próprio."""

    def __init__(self, *, repository: CrmRepositoryPort) -> None:
        """Recebe a porta de repositório por injeção."""
        self._repository = repository

    async def execute(self, *, user_id: str, contact_id: str) -> Contact | None:
        """Arquiva o contato; ``None`` se miss / cross-user."""
        return await self._repository.archive_contact(user_id, contact_id)
