"""Caso de uso: listar/buscar contatos CRM (REQ-002 + paginação)."""
from __future__ import annotations

from dataclasses import dataclass

from src.application.ports.crm_repository import CrmRepositoryPort
from src.domain.crm import Contact


@dataclass(frozen=True)
class PaginatedContacts:
    """Envelope paginado de contatos para API/UI."""

    items: list[Contact]
    total: int
    page: int
    page_size: int


class ListCrmContacts:
    """Lista contatos do usuário, com busca, filtro e paginação."""

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
        page: int = 1,
        page_size: int = 20,
    ) -> PaginatedContacts:
        """Retorna página de contatos do `user_id` com total filtrado."""
        safe_page = max(1, page)
        safe_size = max(1, min(page_size, 100))
        result = await self._repository.list_contacts_page(
            user_id,
            query=query,
            company_id=company_id,
            include_archived=include_archived,
            page=safe_page,
            page_size=safe_size,
        )
        return PaginatedContacts(
            items=result.items,
            total=result.total,
            page=safe_page,
            page_size=safe_size,
        )
