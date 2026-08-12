"""Caso de uso: criar lead CRM (REQ-001 lead-triage-pipeline)."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from src.application.ports.crm_repository import CrmRepositoryPort
from src.domain.crm import Lead, LeadSource
from src.domain.shared.errors import DomainError


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


class CreateCrmLead:
    """Cria um lead escopado ao `user_id` autenticado; status default = new."""

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
        company_name: str | None = None,
        interest: str | None = None,
        estimated_value: Decimal | None = None,
        currency: str | None = None,
        qualification_score: int | None = None,
        notes: str | None = None,
        tags: list[str] | None = None,
        custom_values: dict[str, Any] | None = None,
        source: LeadSource | None = None,
    ) -> Lead:
        """Valida `name` e ao menos um identificador, então persiste o lead.

        Raises:
            DomainError: `name` vazio, sem email/phone/company_name, ou
                `qualification_score` fora de 0-100.
        """
        cleaned_name = name.strip() if name else ""
        cleaned_email = _clean_optional(email)
        cleaned_phone = _clean_optional(phone)
        cleaned_company_name = _clean_optional(company_name)
        if not cleaned_name:
            raise DomainError("Lead.name é obrigatório e não pode ser vazio.")
        if not cleaned_email and not cleaned_phone and not cleaned_company_name:
            raise DomainError(
                "Lead exige ao menos um identificador: "
                "email, phone ou company_name."
            )
        if qualification_score is not None and not 0 <= qualification_score <= 100:
            raise DomainError("qualification_score deve estar entre 0 e 100.")

        now = datetime.now(UTC)
        lead = Lead(
            id=str(uuid.uuid4()),
            user_id=user_id,
            name=cleaned_name,
            email=cleaned_email,
            phone=cleaned_phone,
            company_name=cleaned_company_name,
            interest=_clean_optional(interest),
            estimated_value=estimated_value,
            currency=currency,
            qualification_score=qualification_score,
            notes=notes,
            tags=list(tags) if tags else [],
            custom_values=dict(custom_values or {}),
            source=source,
            created_at=now,
            updated_at=now,
        )
        return await self._repository.create_lead(lead)
