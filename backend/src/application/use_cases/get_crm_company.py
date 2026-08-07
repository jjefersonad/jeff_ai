"""Caso de uso: obter empresa CRM (REQ-002 / REQ-005 crm-companies)."""
from __future__ import annotations

from src.application.ports.crm_repository import CrmRepositoryPort
from src.domain.crm import Company


class GetCrmCompany:
    """Obtém uma empresa do usuário autenticado (miss → None)."""

    def __init__(self, *, repository: CrmRepositoryPort) -> None:
        """Recebe a porta de repositório por injeção."""
        self._repository = repository

    async def execute(self, *, user_id: str, company_id: str) -> Company | None:
        """Retorna a empresa própria ou ``None`` (inclui cross-user)."""
        return await self._repository.get_company(user_id, company_id)
