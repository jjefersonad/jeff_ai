"""Caso de uso: arquivar deal CRM (REQ-005 / REQ-006 crm-deals)."""
from __future__ import annotations

from src.application.ports.crm_repository import CrmRepositoryPort
from src.domain.crm import Deal


class ArchiveCrmDeal:
    """Soft-archive de um deal próprio."""

    def __init__(self, *, repository: CrmRepositoryPort) -> None:
        """Recebe a porta de repositório por injeção."""
        self._repository = repository

    async def execute(self, *, user_id: str, deal_id: str) -> Deal | None:
        """Arquiva o deal; ``None`` se miss / cross-user."""
        return await self._repository.archive_deal(user_id, deal_id)
