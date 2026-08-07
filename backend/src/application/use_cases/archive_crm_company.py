"""Caso de uso: arquivar empresa CRM (REQ-003 / REQ-005 crm-companies)."""
from __future__ import annotations

from src.application.ports.crm_repository import CrmRepositoryPort
from src.domain.crm import Company


class ArchiveCrmCompany:
    """Soft-archive de uma empresa própria."""

    def __init__(self, *, repository: CrmRepositoryPort) -> None:
        """Recebe a porta de repositório por injeção."""
        self._repository = repository

    async def execute(self, *, user_id: str, company_id: str) -> Company | None:
        """Arquiva a empresa; ``None`` se miss / cross-user."""
        return await self._repository.archive_company(user_id, company_id)
