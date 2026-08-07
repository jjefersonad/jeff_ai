"""Caso de uso: criar empresa CRM (REQ-001 crm-companies)."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from src.application.ports.crm_repository import CrmRepositoryPort
from src.domain.crm import Company
from src.domain.shared.errors import DomainError


class CreateCrmCompany:
    """Cria uma empresa escopada ao `user_id` autenticado."""

    def __init__(self, *, repository: CrmRepositoryPort) -> None:
        """Recebe a porta de repositório por injeção."""
        self._repository = repository

    async def execute(
        self,
        *,
        user_id: str,
        name: str,
        website: str | None = None,
        domain: str | None = None,
        phone: str | None = None,
        notes: str | None = None,
    ) -> Company:
        """Valida `name` e persiste a empresa.

        Raises:
            DomainError: se `name` estiver vazio.
        """
        cleaned_name = name.strip() if name else ""
        if not cleaned_name:
            raise DomainError("Company.name é obrigatório e não pode ser vazio.")

        now = datetime.now(UTC)
        company = Company(
            id=str(uuid.uuid4()),
            user_id=user_id,
            name=cleaned_name,
            website=website.strip() if website else None,
            domain=domain.strip() if domain else None,
            phone=phone.strip() if phone else None,
            notes=notes,
            created_at=now,
            updated_at=now,
        )
        return await self._repository.create_company(company)
