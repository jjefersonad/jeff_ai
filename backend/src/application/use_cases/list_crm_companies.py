"""Caso de uso: listar/buscar empresas CRM (REQ-002 crm-companies)."""
from __future__ import annotations

from src.application.ports.crm_repository import CrmRepositoryPort
from src.domain.crm import Company


class ListCrmCompanies:
    """Lista empresas do usuário, com busca e filtro de arquivados."""

    def __init__(self, *, repository: CrmRepositoryPort) -> None:
        """Recebe a porta de repositório por injeção."""
        self._repository = repository

    async def execute(
        self,
        *,
        user_id: str,
        query: str | None = None,
        include_archived: bool = False,
    ) -> list[Company]:
        """Retorna só empresas do `user_id`."""
        return await self._repository.list_companies(
            user_id,
            query=query,
            include_archived=include_archived,
        )
