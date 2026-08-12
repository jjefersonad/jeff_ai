"""Testes dos use cases de leads CRM (sales-pipeline-via-agent-task-backend-leads-1).

Unit-1: create rejeita lead sem email/phone/company_name
Unit-2: create happy path com name+phone
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.application.ports.crm_repository import CrmRepositoryPort
from crm_repository_fakes import CrmRepositoryPortExtensions
from src.domain.crm import Company, Contact, Deal, DealStage, Lead, LeadStatus, Note
from src.domain.shared.errors import DomainError


class _FakeCrmRepository(CrmRepositoryPortExtensions, CrmRepositoryPort):
    def __init__(self) -> None:
        self.leads: dict[str, Lead] = {}
        self.create_calls = 0

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
        self.create_calls += 1
        self.leads[lead.id] = lead
        return lead

    async def list_leads(
        self, user_id: str, *, converted: bool = False
    ) -> list[Lead]:
        items = [
            lead for lead in self.leads.values() if lead.user_id == user_id
        ]
        if converted:
            return [lead for lead in items if lead.converted_at is not None]
        return [lead for lead in items if lead.converted_at is None]


async def test_create_lead_rejects_missing_contact_info() -> None:
    """unit-1 (REQ-001): sem email/phone/company_name -> DomainError, não persiste."""
    from src.application.use_cases.create_crm_lead import CreateCrmLead

    repo = _FakeCrmRepository()
    uc = CreateCrmLead(repository=repo)

    with pytest.raises(DomainError, match="email|phone|company_name"):
        await uc.execute(user_id="user-a", name="Só Nome")

    assert repo.create_calls == 0
    assert repo.leads == {}


async def test_create_lead_happy_path_with_phone() -> None:
    """unit-2 (REQ-001): name+phone -> lead com id e status default new."""
    from src.application.use_cases.create_crm_lead import CreateCrmLead

    repo = _FakeCrmRepository()
    uc = CreateCrmLead(repository=repo)

    lead = await uc.execute(user_id="user-a", name="João", phone="11999998888")

    assert lead.id
    assert lead.user_id == "user-a"
    assert lead.status == LeadStatus.NEW
    assert repo.create_calls == 1


async def test_list_leads_filters_by_converted() -> None:
    """REQ-002: lista ativos por default; converted=True mostra só convertidos."""
    from src.application.use_cases.create_crm_lead import CreateCrmLead
    from src.application.use_cases.list_crm_leads import ListCrmLeads

    repo = _FakeCrmRepository()
    active = await CreateCrmLead(repository=repo).execute(
        user_id="user-a", name="A", phone="1"
    )
    converted = await CreateCrmLead(repository=repo).execute(
        user_id="user-a", name="B", phone="2"
    )
    repo.leads[converted.id].converted_at = datetime.now(UTC)

    default_list = await ListCrmLeads(repository=repo).execute(user_id="user-a")
    assert [lead.id for lead in default_list] == [active.id]

    converted_list = await ListCrmLeads(repository=repo).execute(
        user_id="user-a", converted=True
    )
    assert [lead.id for lead in converted_list] == [converted.id]
