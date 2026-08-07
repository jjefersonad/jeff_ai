"""Caso de uso: criar contato CRM (REQ-001 crm-contacts)."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from src.application.ports.crm_repository import CrmRepositoryPort
from src.domain.crm import Contact
from src.domain.shared.errors import DomainError


class CreateCrmContact:
    """Cria um contato escopado ao `user_id` autenticado."""

    def __init__(self, *, repository: CrmRepositoryPort) -> None:
        """Recebe a porta de repositório por injeção."""
        self._repository = repository

    async def execute(
        self,
        *,
        user_id: str,
        name: str,
        email: str | None = None,
        phone: str | None = None,
        company_id: str | None = None,
        status: str | None = None,
        tags: list[str] | None = None,
    ) -> Contact:
        """Valida identificador (email ou phone) e persiste o contato.

        Raises:
            DomainError: se `name` vazio ou sem email e phone.
        """
        cleaned_name = name.strip() if name else ""
        cleaned_email = email.strip() if email else None
        cleaned_phone = phone.strip() if phone else None
        if not cleaned_name:
            raise DomainError("Contact.name é obrigatório e não pode ser vazio.")
        if not cleaned_email and not cleaned_phone:
            raise DomainError(
                "Contact exige ao menos um identificador: email ou phone."
            )
        if company_id is not None:
            company = await self._repository.get_company(user_id, company_id)
            if company is None:
                raise DomainError("company_id inválido para este usuário.")

        now = datetime.now(UTC)
        contact = Contact(
            id=str(uuid.uuid4()),
            user_id=user_id,
            name=cleaned_name,
            email=cleaned_email or None,
            phone=cleaned_phone or None,
            company_id=company_id,
            status=status,
            tags=list(tags) if tags else [],
            created_at=now,
            updated_at=now,
        )
        return await self._repository.create_contact(contact)
