"""Caso de uso: atualizar empresa CRM (REQ-003 crm-companies)."""
from __future__ import annotations

from datetime import UTC, datetime

from src.application.ports.crm_repository import CrmRepositoryPort
from src.domain.crm import Company
from src.domain.shared.errors import DomainError


class UpdateCrmCompany:
    """Atualiza campos mutáveis de uma empresa própria."""

    def __init__(self, *, repository: CrmRepositoryPort) -> None:
        """Recebe a porta de repositório por injeção."""
        self._repository = repository

    async def execute(
        self,
        *,
        user_id: str,
        company_id: str,
        name: str | None = None,
        website: str | None = None,
        domain: str | None = None,
        phone: str | None = None,
        notes: str | None = None,
    ) -> Company | None:
        """Atualiza a empresa; ``None`` se miss / cross-user.

        Raises:
            DomainError: se `name` ficar vazio.
        """
        existing = await self._repository.get_company(user_id, company_id)
        if existing is None:
            return None

        new_name = name.strip() if name is not None else existing.name
        if not new_name:
            raise DomainError("Company.name é obrigatório e não pode ser vazio.")

        updated = Company(
            id=existing.id,
            user_id=existing.user_id,
            name=new_name,
            website=(
                existing.website if website is None else (website.strip() or None)
            ),
            domain=existing.domain if domain is None else (domain.strip() or None),
            phone=existing.phone if phone is None else (phone.strip() or None),
            notes=existing.notes if notes is None else notes,
            archived_at=existing.archived_at,
            created_at=existing.created_at,
            updated_at=datetime.now(UTC),
        )
        return await self._repository.update_company(updated)
