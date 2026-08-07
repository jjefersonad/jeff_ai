"""Caso de uso: listar/buscar contatos CRM (REQ-002 crm-contacts)."""
from __future__ import annotations

from src.application.ports.crm_repository import CrmRepositoryPort
from src.domain.crm import Contact


class ListCrmContacts:
    """Lista contatos do usuário, com busca e filtro de arquivados."""

    def __init__(self, *, repository: CrmRepositoryPort) -> None:
        """Recebe a porta de repositório por injeção."""
        self._repository = repository

    async def execute(
        self,
        *,
        user_id: str,
        query: str | None = None,
        company_id: str | None = None,
        include_archived: bool = False,
    ) -> list[Contact]:
        """Retorna só contatos do `user_id` (REQ-002)."""
        return await self._repository.list_contacts(
            user_id,
            query=query,
            company_id=company_id,
            include_archived=include_archived,
        )
