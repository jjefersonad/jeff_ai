"""Caso de uso: criar deal CRM (REQ-002 crm-deals + custom_values).

Orquestra contato opcional no mesmo fluxo (`correct-funil-lead-as-deal`):
create/update via `CreateCrmContact` / `UpdateCrmContact`; lookup por
e-mail quando não há `contact_id`; nome vazio cai no título do deal.
Validação de contato que falha não persiste o deal.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from src.application.ports.crm_repository import CrmRepositoryPort
from src.application.use_cases.create_crm_contact import CreateCrmContact
from src.application.use_cases.crm_custom_values import validate_custom_values
from src.application.use_cases.update_crm_contact import UpdateCrmContact
from src.domain.crm import Deal, DealStage, FieldEntity
from src.domain.shared.errors import DomainError


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _has_contact_payload(
    *,
    contact_name: str | None,
    email: str | None,
    phone: str | None,
    city: str | None,
    state: str | None,
    tags: list[str] | None,
    status: str | None,
    contact_custom_values: dict[str, Any] | None,
) -> bool:
    return bool(
        _clean_optional(contact_name)
        or _clean_optional(email)
        or _clean_optional(phone)
        or _clean_optional(city)
        or _clean_optional(state)
        or tags is not None
        or _clean_optional(status)
        or contact_custom_values is not None
    )


class CreateCrmDeal:
    """Cria um deal escopado ao usuário; stage default = lead."""

    def __init__(self, *, repository: CrmRepositoryPort) -> None:
        """Recebe a porta de repositório por injeção."""
        self._repository = repository

    async def execute(
        self,
        *,
        user_id: str,
        title: str,
        stage: DealStage | None = None,
        value: Decimal | None = None,
        currency: str | None = None,
        contact_id: str | None = None,
        company_id: str | None = None,
        custom_values: dict[str, Any] | None = None,
        contact_name: str | None = None,
        email: str | None = None,
        phone: str | None = None,
        city: str | None = None,
        state: str | None = None,
        tags: list[str] | None = None,
        status: str | None = None,
        contact_custom_values: dict[str, Any] | None = None,
    ) -> Deal:
        """Valida vínculos, orquestra contato opcional e persiste o deal.

        Raises:
            DomainError: title vazio, contact/company alienígenas, ou
                contato sem email e phone.
        """
        cleaned_title = title.strip() if title else ""
        if not cleaned_title:
            raise DomainError("Deal.title é obrigatório e não pode ser vazio.")

        if company_id is not None:
            if await self._repository.get_company(user_id, company_id) is None:
                raise DomainError("company_id inválido para este usuário.")

        resolved_currency = currency
        if value is not None and not resolved_currency:
            resolved_currency = "BRL"

        definitions = await self._repository.list_field_definitions(
            user_id, entity=FieldEntity.DEAL
        )
        values = validate_custom_values(
            definitions=definitions,
            existing={},
            incoming=custom_values,
        )

        resolved_contact_id = await self._resolve_contact_id(
            user_id=user_id,
            title=cleaned_title,
            contact_id=contact_id,
            contact_name=contact_name,
            email=email,
            phone=phone,
            city=city,
            state=state,
            tags=tags,
            status=status,
            contact_custom_values=contact_custom_values,
        )

        now = datetime.now(UTC)
        deal = Deal(
            id=str(uuid.uuid4()),
            user_id=user_id,
            title=cleaned_title,
            stage=stage or DealStage.LEAD,
            value=value,
            currency=resolved_currency,
            contact_id=resolved_contact_id,
            company_id=company_id,
            custom_values=values,
            created_at=now,
            updated_at=now,
        )
        return await self._repository.create_deal(deal)

    async def _resolve_contact_id(
        self,
        *,
        user_id: str,
        title: str,
        contact_id: str | None,
        contact_name: str | None,
        email: str | None,
        phone: str | None,
        city: str | None,
        state: str | None,
        tags: list[str] | None,
        status: str | None,
        contact_custom_values: dict[str, Any] | None,
    ) -> str | None:
        wants_contact = _has_contact_payload(
            contact_name=contact_name,
            email=email,
            phone=phone,
            city=city,
            state=state,
            tags=tags,
            status=status,
            contact_custom_values=contact_custom_values,
        )
        if not wants_contact:
            if contact_id is not None:
                if await self._repository.get_contact(user_id, contact_id) is None:
                    raise DomainError("contact_id inválido para este usuário.")
            return contact_id

        update = UpdateCrmContact(repository=self._repository)
        target_id = contact_id
        if target_id is None:
            cleaned_email = _clean_optional(email)
            if cleaned_email is not None:
                matched = await self._repository.get_contact_by_email(
                    user_id, cleaned_email
                )
                if matched is not None:
                    target_id = matched.id

        if target_id is not None:
            updated = await update.execute(
                user_id=user_id,
                contact_id=target_id,
                name=_clean_optional(contact_name),
                email=email,
                phone=phone,
                city=city,
                state=state,
                tags=tags,
                status=status,
                custom_values=contact_custom_values,
            )
            if updated is None:
                raise DomainError("contact_id inválido para este usuário.")
            return updated.id

        created = await CreateCrmContact(repository=self._repository).execute(
            user_id=user_id,
            name=_clean_optional(contact_name) or title,
            email=email,
            phone=phone,
            city=city,
            state=state,
            tags=tags,
            status=status,
            custom_values=contact_custom_values,
        )
        return created.id
