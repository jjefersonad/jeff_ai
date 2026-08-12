"""Caso de uso: converter lead em Contato+Empresa+Deal (REQ-003 lead-triage-pipeline)."""
from __future__ import annotations

from src.application.ports.crm_repository import CrmRepositoryPort, LeadConversionResult
from src.domain.shared.errors import DomainError


class ConvertCrmLead:
    """Converte um lead elegível numa transação atômica (contato+empresa+deal)."""

    def __init__(self, *, repository: CrmRepositoryPort) -> None:
        """Recebe a porta de repositório por injeção."""
        self._repository = repository

    async def execute(
        self, *, user_id: str, lead_id: str
    ) -> LeadConversionResult | None:
        """Valida elegibilidade e delega a transação ao repositório.

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
        return await self._repository.convert_lead(lead)
