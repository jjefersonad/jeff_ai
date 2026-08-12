"""Testes do use case `PreviewCrmLeadConversion` (sales-pipeline-via-agent-task-backend-leads-3).

Unit-1: preview indica `company_is_new` corretamente (empresa nova vs.
existente), sem escrever nenhuma linha.
"""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

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
        self.companies: dict[str, Company] = {}
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

    async def get_company_by_name(self, user_id: str, name: str) -> Company | None:
        for company in self.companies.values():
            if company.user_id == user_id and company.name.lower() == name.lower():
                return company
        return None

    async def convert_lead(self, lead: Lead) -> LeadConversionResult:
        self.convert_calls += 1
        raise AssertionError("preview não deve chamar convert_lead")


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


async def test_preview_company_is_new_when_no_match() -> None:
    """unit-1 (REQ-004): company_name inédito -> company_is_new=True, sem escrita."""
    from src.application.use_cases.preview_crm_lead_conversion import (
        PreviewCrmLeadConversion,
    )

    repo = _FakeCrmRepository()
    await _seed_lead(
        repo, company_name="Acme Ltda", estimated_value=Decimal("1500.00")
    )

    preview = await PreviewCrmLeadConversion(repository=repo).execute(
        user_id="user-a", lead_id="lead-1"
    )

    assert preview is not None
    assert preview.contact_name == "João"
    assert preview.company_name == "Acme Ltda"
    assert preview.company_is_new is True
    assert preview.deal_value == Decimal("1500.00")
    assert repo.convert_calls == 0
    assert repo.leads["lead-1"].converted_at is None


async def test_preview_company_is_new_false_when_company_exists() -> None:
    """unit-1 (REQ-004): company_name já existe -> company_is_new=False, sem escrita."""
    from src.application.use_cases.preview_crm_lead_conversion import (
        PreviewCrmLeadConversion,
    )

    repo = _FakeCrmRepository()
    repo.companies["company-1"] = Company(
        id="company-1",
        user_id="user-a",
        name="Acme Ltda",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    await _seed_lead(repo, company_name="acme ltda")

    preview = await PreviewCrmLeadConversion(repository=repo).execute(
        user_id="user-a", lead_id="lead-1"
    )

    assert preview is not None
    assert preview.company_is_new is False
    assert repo.convert_calls == 0


async def test_preview_not_found_returns_none() -> None:
    """Lead inexistente/cross-user -> None."""
    from src.application.use_cases.preview_crm_lead_conversion import (
        PreviewCrmLeadConversion,
    )

    repo = _FakeCrmRepository()
    preview = await PreviewCrmLeadConversion(repository=repo).execute(
        user_id="user-a", lead_id="does-not-exist"
    )
    assert preview is None


async def test_preview_already_converted_raises() -> None:
    """Lead já convertido -> DomainError, sem escrita."""
    from src.application.use_cases.preview_crm_lead_conversion import (
        PreviewCrmLeadConversion,
    )

    repo = _FakeCrmRepository()
    await _seed_lead(repo, converted_at=datetime.now(UTC))

    with pytest.raises(DomainError, match="convertido"):
        await PreviewCrmLeadConversion(repository=repo).execute(
            user_id="user-a", lead_id="lead-1"
        )
