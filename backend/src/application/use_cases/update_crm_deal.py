"""Caso de uso: atualizar deal CRM (título, valor, empresa, contato, estágio).

Reusa a orquestração de contato de `CreateCrmDeal` (create/update por
e-mail). Mudança de estágio passa por `MoveCrmDeal` para gravar a nota
de transição.
"""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from src.application.ports.crm_repository import CrmRepositoryPort
from src.application.use_cases.create_crm_deal import CreateCrmDeal
from src.application.use_cases.move_crm_deal import MoveCrmDeal
from src.domain.crm import Deal, DealStage, NoteSource
from src.domain.shared.errors import DomainError


class UpdateCrmDeal:
    """Atualiza campos mutáveis de um deal próprio."""

    def __init__(self, *, repository: CrmRepositoryPort) -> None:
        """Recebe a porta de repositório por injeção."""
        self._repository = repository

    async def execute(
        self,
        *,
        user_id: str,
        deal_id: str,
        title: str | None = None,
        stage: DealStage | None = None,
        value: Decimal | None = None,
        set_value: bool = False,
        currency: str | None = None,
        company_id: str | None = None,
        clear_company: bool = False,
        contact_name: str | None = None,
        email: str | None = None,
        phone: str | None = None,
        city: str | None = None,
        state: str | None = None,
        tags: list[str] | None = None,
        status: str | None = None,
        contact_custom_values: dict[str, Any] | None = None,
        apply_contact: bool = False,
        source: NoteSource = NoteSource.USER,
    ) -> Deal | None:
        """Atualiza o deal; ``None`` se miss / cross-user.

        Raises:
            DomainError: title vazio, company/contact inválidos, ou
                contato sem email e phone.
        """
        existing = await self._repository.get_deal(user_id, deal_id)
        if existing is None:
            return None

        cleaned_title = existing.title
        if title is not None:
            cleaned_title = title.strip()
            if not cleaned_title:
                raise DomainError("Deal.title é obrigatório e não pode ser vazio.")

        if clear_company:
            new_company_id: str | None = None
        elif company_id is not None:
            if await self._repository.get_company(user_id, company_id) is None:
                raise DomainError("company_id inválido para este usuário.")
            new_company_id = company_id
        else:
            new_company_id = existing.company_id

        new_value = value if set_value else existing.value
        if set_value and new_value is not None and not currency:
            new_currency = existing.currency or "BRL"
        elif set_value and new_value is None:
            new_currency = None
        else:
            new_currency = currency if currency is not None else existing.currency

        resolved_contact_id = existing.contact_id
        if apply_contact:
            resolved_contact_id = await CreateCrmDeal(
                repository=self._repository
            )._resolve_contact_id(
                user_id=user_id,
                title=cleaned_title,
                contact_id=existing.contact_id,
                contact_name=contact_name,
                email=email,
                phone=phone,
                city=city,
                state=state,
                tags=tags,
                status=status,
                contact_custom_values=contact_custom_values,
            )

        updated = Deal(
            id=existing.id,
            user_id=existing.user_id,
            title=cleaned_title,
            stage=existing.stage,
            value=new_value,
            currency=new_currency,
            contact_id=resolved_contact_id,
            company_id=new_company_id,
            custom_values=existing.custom_values,
            archived_at=existing.archived_at,
            created_at=existing.created_at,
            updated_at=datetime.now(UTC),
        )
        stored = await self._repository.update_deal(updated)
        if stored is None:
            return None

        if stage is not None and stage != stored.stage:
            moved = await MoveCrmDeal(repository=self._repository).execute(
                user_id=user_id,
                deal_id=stored.id,
                stage=stage,
                source=source,
            )
            return moved if moved is not None else stored
        return stored
