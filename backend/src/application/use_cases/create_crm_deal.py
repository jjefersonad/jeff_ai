"""Caso de uso: criar deal CRM (REQ-002 crm-deals)."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from src.application.ports.crm_repository import CrmRepositoryPort
from src.domain.crm import Deal, DealStage
from src.domain.shared.errors import DomainError


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
    ) -> Deal:
        """Valida vínculos e persiste o deal.

        Raises:
            DomainError: title vazio ou contact/company alienígenas.
        """
        cleaned_title = title.strip() if title else ""
        if not cleaned_title:
            raise DomainError("Deal.title é obrigatório e não pode ser vazio.")

        if contact_id is not None:
            if await self._repository.get_contact(user_id, contact_id) is None:
                raise DomainError("contact_id inválido para este usuário.")
        if company_id is not None:
            if await self._repository.get_company(user_id, company_id) is None:
                raise DomainError("company_id inválido para este usuário.")

        resolved_currency = currency
        if value is not None and not resolved_currency:
            resolved_currency = "BRL"

        now = datetime.now(UTC)
        deal = Deal(
            id=str(uuid.uuid4()),
            user_id=user_id,
            title=cleaned_title,
            stage=stage or DealStage.LEAD,
            value=value,
            currency=resolved_currency,
            contact_id=contact_id,
            company_id=company_id,
            created_at=now,
            updated_at=now,
        )
        return await self._repository.create_deal(deal)
