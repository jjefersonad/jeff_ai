"""Caso de uso: preview (dry-run) de conversão de lead (REQ-004 lead-triage-pipeline)."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from src.application.ports.crm_repository import CrmRepositoryPort
from src.domain.shared.errors import DomainError


@dataclass(frozen=True)
class LeadConversionPreview:
    """O que `convert_lead` criaria, sem escrever nada no banco."""

    contact_name: str
    company_name: str | None
    company_is_new: bool
    deal_value: Decimal | None


class PreviewCrmLeadConversion:
    """Mostra o que a conversão criaria, sem persistir nada."""

    def __init__(self, *, repository: CrmRepositoryPort) -> None:
        """Recebe a porta de repositório por injeção."""
        self._repository = repository

    async def execute(
        self, *, user_id: str, lead_id: str
    ) -> LeadConversionPreview | None:
        """Valida elegibilidade (mesmas regras de `ConvertCrmLead`) e monta o preview.

        Raises:
            DomainError: lead já convertido ou arquivado.
        """
        lead = await self._repository.get_lead(user_id, lead_id)
        if lead is None:
            return None
        if lead.converted_at is not None:
            raise DomainError("Lead já foi convertido.")
        if lead.archived_at is not None:
            raise DomainError("Lead arquivado não pode ser convertido.")

        company_is_new = True
        if lead.company_name:
            existing = await self._repository.get_company_by_name(
                user_id, lead.company_name
            )
            company_is_new = existing is None

        return LeadConversionPreview(
            contact_name=lead.name,
            company_name=lead.company_name,
            company_is_new=company_is_new,
            deal_value=lead.estimated_value,
        )
