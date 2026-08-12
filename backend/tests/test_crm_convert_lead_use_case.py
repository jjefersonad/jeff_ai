"""Testes do use case `ConvertCrmLead` (sales-pipeline-via-agent-task-backend-leads-2).

Guardas de negócio (lead não encontrado / já convertido / arquivado) — a
transação atômica em si é coberta por integração real em test_crm_repository.py,
já que fakes não conseguem exercitar rollback de verdade.
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.application.ports.crm_repository import (
    CrmRepositoryPort,
    LeadConversionResult,
)
from crm_repository_fakes import CrmRepositoryPortExtensions
from src.domain.crm import Company, Contact, Deal, DealStage, Lead, Note
from src.domain.shared.errors import DomainError


class _FakeCrmRepository(CrmRepositoryPortExtensions, CrmRepositoryPort):
    def __init__(self) -> None:
        self.leads: dict[str, Lead] = {}
        self.convert_calls = 0

    async def create_company(self, company: Company) -> Company:
        raise NotImplementedError

    async def get_company(self, user_id: str, company_id: str) -> Company | None:
        return None

    async def list_companies(
        self,
        user_id: str,
        *,
        query: str | None = None,
        include_archived: bool = False,
    ) -> list[Company]:
        return []

    async def update_company(self, company: Company) -> Company | None:
        return None

    async def archive_company(self, user_id: str, company_id: str) -> Company | None:
        return None

    async def create_contact(self, contact: Contact) -> Contact:
        raise NotImplementedError

    async def get_contact(self, user_id: str, contact_id: str) -> Contact | None:
        return None

    async def list_contacts(
        self,
        user_id: str,
        *,
        query: str | None = None,
        company_id: str | None = None,
        include_archived: bool = False,
    ) -> list[Contact]:
        return []

    async def update_contact(self, contact: Contact) -> Contact | None:
        return None

    async def archive_contact(self, user_id: str, contact_id: str) -> Contact | None:
        return None

    async def create_deal(self, deal: Deal) -> Deal:
        raise NotImplementedError

    async def get_deal(self, user_id: str, deal_id: str) -> Deal | None:
        return None

    async def list_deals(
        self,
        user_id: str,
        *,
        stage: DealStage | None = None,
        include_archived: bool = False,
    ) -> list[Deal]:
        return []

    async def update_deal(self, deal: Deal) -> Deal | None:
        return None

    async def archive_deal(self, user_id: str, deal_id: str) -> Deal | None:
        return None

    async def move_deal(
        self, user_id: str, deal_id: str, stage: DealStage
    ) -> Deal | None:
        return None

    async def create_note(self, note: Note) -> Note:
        raise NotImplementedError

    async def list_notes_for_contact(
        self,
        user_id: str,
        contact_id: str,
        *,
        include_archived: bool = False,
    ) -> list[Note]:
        return []

    async def list_notes_for_company(
        self,
        user_id: str,
        company_id: str,
        *,
        include_archived: bool = False,
    ) -> list[Note]:
        return []

    async def list_notes_for_deal(
        self,
        user_id: str,
        deal_id: str,
        *,
        include_archived: bool = False,
    ) -> list[Note]:
        return []

    async def create_lead(self, lead: Lead) -> Lead:
        self.leads[lead.id] = lead
        return lead

    async def list_leads(
        self, user_id: str, *, converted: bool = False
    ) -> list[Lead]:
        return []

    async def get_lead(self, user_id: str, lead_id: str) -> Lead | None:
        lead = self.leads.get(lead_id)
        if lead is None or lead.user_id != user_id:
            return None
        return lead

    async def convert_lead(self, lead: Lead) -> LeadConversionResult:
        self.convert_calls += 1
        contact = Contact(
            id="contact-1", user_id=lead.user_id, name=lead.name,
            source_lead_id=lead.id,
        )
        deal = Deal(
            id="deal-1", user_id=lead.user_id, title=lead.name,
            source_lead_id=lead.id,
        )
        return LeadConversionResult(lead=lead, contact=contact, company=None, deal=deal)


async def _seed_lead(repo: _FakeCrmRepository, **overrides: object) -> Lead:
    defaults: dict[str, object] = dict(
        id="lead-1",
        user_id="user-a",
        name="João",
        phone="11999998888",
    )
    defaults.update(overrides)
    lead = Lead(**defaults)  # type: ignore[arg-type]
    repo.leads[lead.id] = lead
    return lead


async def test_convert_lead_not_found_returns_none() -> None:
    """Lead inexistente/cross-user -> None, sem chamar convert_lead."""
    from src.application.use_cases.convert_crm_lead import ConvertCrmLead

    repo = _FakeCrmRepository()
    result = await ConvertCrmLead(repository=repo).execute(
        user_id="user-a", lead_id="does-not-exist"
    )
    assert result is None
    assert repo.convert_calls == 0


async def test_convert_lead_already_converted_raises() -> None:
    """Lead já convertido -> DomainError, sem duplicar."""
    from src.application.use_cases.convert_crm_lead import ConvertCrmLead

    repo = _FakeCrmRepository()
    await _seed_lead(repo, converted_at=datetime.now(UTC))

    with pytest.raises(DomainError, match="convertido"):
        await ConvertCrmLead(repository=repo).execute(
            user_id="user-a", lead_id="lead-1"
        )
    assert repo.convert_calls == 0


async def test_convert_lead_archived_raises() -> None:
    """Lead arquivado -> DomainError, sem duplicar."""
    from src.application.use_cases.convert_crm_lead import ConvertCrmLead

    repo = _FakeCrmRepository()
    await _seed_lead(repo, archived_at=datetime.now(UTC))

    with pytest.raises(DomainError, match="arquivado"):
        await ConvertCrmLead(repository=repo).execute(
            user_id="user-a", lead_id="lead-1"
        )
    assert repo.convert_calls == 0


async def test_convert_lead_happy_path_delegates_to_repository() -> None:
    """Lead elegível -> delega para repository.convert_lead exatamente uma vez."""
    from src.application.use_cases.convert_crm_lead import ConvertCrmLead

    repo = _FakeCrmRepository()
    await _seed_lead(repo)

    result = await ConvertCrmLead(repository=repo).execute(
        user_id="user-a", lead_id="lead-1"
    )
    assert result is not None
    assert result.contact.source_lead_id == "lead-1"
    assert result.deal.source_lead_id == "lead-1"
    assert repo.convert_calls == 1
