"""Caso de uso: obter deal CRM (REQ-006 crm-deals)."""
from __future__ import annotations

from src.application.ports.crm_repository import CrmRepositoryPort
from src.domain.crm import Deal


class GetCrmDeal:
    """Obtém um deal do usuário autenticado (miss → None)."""

    def __init__(self, *, repository: CrmRepositoryPort) -> None:
        """Recebe a porta de repositório por injeção."""
        self._repository = repository

    async def execute(self, *, user_id: str, deal_id: str) -> Deal | None:
        """Retorna o deal próprio ou ``None`` (inclui cross-user)."""
        return await self._repository.get_deal(user_id, deal_id)
