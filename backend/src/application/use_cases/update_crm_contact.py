"""Caso de uso: atualizar contato CRM (REQ-003 / REQ-005 crm-contacts)."""
from __future__ import annotations

from datetime import UTC, datetime

from src.application.ports.crm_repository import CrmRepositoryPort
from src.domain.crm import Contact
from src.domain.shared.errors import DomainError


class UpdateCrmContact:
    """Atualiza campos mutáveis de um contato próprio."""

    def __init__(self, *, repository: CrmRepositoryPort) -> None:
        """Recebe a porta de repositório por injeção."""
        self._repository = repository

    async def execute(
        self,
        *,
        user_id: str,
        contact_id: str,
        name: str | None = None,
        email: str | None = None,
        phone: str | None = None,
        company_id: str | None = None,
        clear_company: bool = False,
        status: str | None = None,
        tags: list[str] | None = None,
    ) -> Contact | None:
        """Atualiza o contato; ``None`` se miss / cross-user.

        Raises:
            DomainError: se o resultado ficar sem email e sem phone, ou
                `company_id` inválido para o usuário.
        """
        existing = await self._repository.get_contact(user_id, contact_id)
        if existing is None:
            return None

        new_name = name.strip() if name is not None else existing.name
        if not new_name:
            raise DomainError("Contact.name é obrigatório e não pode ser vazio.")

        new_email = existing.email if email is None else (email.strip() or None)
        new_phone = existing.phone if phone is None else (phone.strip() or None)
        if not new_email and not new_phone:
            raise DomainError(
                "Contact exige ao menos um identificador: email ou phone."
            )

        if clear_company:
            new_company_id: str | None = None
        elif company_id is not None:
            company = await self._repository.get_company(user_id, company_id)
            if company is None:
                raise DomainError("company_id inválido para este usuário.")
            new_company_id = company_id
        else:
            new_company_id = existing.company_id

        updated = Contact(
            id=existing.id,
            user_id=existing.user_id,
            name=new_name,
            email=new_email,
            phone=new_phone,
            company_id=new_company_id,
            status=existing.status if status is None else status,
            tags=existing.tags if tags is None else list(tags),
            archived_at=existing.archived_at,
            created_at=existing.created_at,
            updated_at=datetime.now(UTC),
        )
        return await self._repository.update_contact(updated)
