"""Testes de `POST /api/crm/leads/{id}/convert` (sales-pipeline-via-agent-task-backend-leads-3).

Unit-1: preview indica `company_is_new` corretamente, sem escrever nada.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

import src.infrastructure.web.crm_router as crm_router
from src.application.ports.crm_repository import (
    CrmRepositoryPort,
    LeadConversionResult,
)
from crm_repository_fakes import CrmRepositoryPortExtensions
from src.domain.crm import Company, Contact, Deal, DealStage, Lead, Note
from src.infrastructure.auth.dependencies import require_auth
from src.infrastructure.auth.users import User

_USER_A = User(
    id="user-a",
    username="alice",
    password_hash="h",
    role="user",
    is_active=True,
    created_at=datetime(2026, 1, 1, tzinfo=UTC),
)


class _FakeCrmRepository(CrmRepositoryPortExtensions, CrmRepositoryPort):
    def __init__(self) -> None:
        self.leads: dict[str, Lead] = {}
        self.companies: dict[str, Company] = {}
        self.contacts: dict[str, Contact] = {}
        self.deals: dict[str, Deal] = {}

    async def create_company(self, company: Company) -> Company:
        raise NotImplementedError

    async def get_company(self, user_id: str, company_id: str) -> Company | None:
        return None

    async def get_company_by_name(self, user_id: str, name: str) -> Company | None:
        for company in self.companies.values():
            if company.user_id == user_id and company.name.lower() == name.lower():
                return company
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
        """Simula a transação atômica em memória (a real é integração em
        test_crm_repository.py)."""
        now = datetime.now(UTC)
        company: Company | None = None
        if lead.company_name:
            company = await self.get_company_by_name(lead.user_id, lead.company_name)
            if company is None:
                company = Company(
                    id=str(uuid.uuid4()),
                    user_id=lead.user_id,
                    name=lead.company_name,
                    source_lead_id=lead.id,
                    created_at=now,
                    updated_at=now,
                )
                self.companies[company.id] = company
        contact = Contact(
            id=str(uuid.uuid4()),
            user_id=lead.user_id,
            name=lead.name,
            email=lead.email,
            phone=lead.phone,
            company_id=company.id if company is not None else None,
            source_lead_id=lead.id,
            created_at=now,
            updated_at=now,
        )
        self.contacts[contact.id] = contact
        deal = Deal(
            id=str(uuid.uuid4()),
            user_id=lead.user_id,
            title=lead.name,
            stage=DealStage.QUALIFIED,
            value=lead.estimated_value,
            currency=lead.currency,
            contact_id=contact.id,
            company_id=company.id if company is not None else None,
            source_lead_id=lead.id,
            created_at=now,
            updated_at=now,
        )
        self.deals[deal.id] = deal
        lead.converted_at = now
        lead.converted_contact_id = contact.id
        lead.converted_company_id = company.id if company is not None else None
        lead.converted_deal_id = deal.id
        self.leads[lead.id] = lead
        return LeadConversionResult(
            lead=lead, contact=contact, company=company, deal=deal
        )


def _client(repo: _FakeCrmRepository) -> TestClient:
    app = FastAPI(dependencies=[Depends(require_auth)])
    app.include_router(crm_router.router)
    app.dependency_overrides[crm_router._crm_repository] = lambda: repo
    app.dependency_overrides[require_auth] = lambda: _USER_A
    return TestClient(app)


def _seed_lead(repo: _FakeCrmRepository, **overrides: object) -> Lead:
    defaults: dict[str, object] = dict(
        id=str(uuid.uuid4()),
        user_id="user-a",
        name="João",
        phone="11999998888",
    )
    defaults.update(overrides)
    lead = Lead(**defaults)  # type: ignore[arg-type]
    repo.leads[lead.id] = lead
    return lead


def test_preview_returns_company_is_new_true_and_writes_nothing() -> None:
    """unit-1 (REQ-004): company_name inédito -> company_is_new=True, sem escrita."""
    repo = _FakeCrmRepository()
    lead = _seed_lead(repo, company_name="Acme Ltda")
    client = _client(repo)

    response = client.post(f"/api/crm/leads/{lead.id}/convert?preview=true")

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "contact_name": "João",
        "company_name": "Acme Ltda",
        "company_is_new": True,
        "deal_value": None,
    }
    assert repo.contacts == {}
    assert repo.companies == {}
    assert repo.deals == {}
    assert repo.leads[lead.id].converted_at is None


def test_preview_returns_company_is_new_false_when_company_exists() -> None:
    """unit-1 (REQ-004): company_name já existe -> company_is_new=False, sem escrita."""
    repo = _FakeCrmRepository()
    now = datetime.now(UTC)
    existing = Company(
        id=str(uuid.uuid4()),
        user_id="user-a",
        name="Acme Ltda",
        created_at=now,
        updated_at=now,
    )
    repo.companies[existing.id] = existing
    lead = _seed_lead(repo, company_name="acme ltda")
    client = _client(repo)

    response = client.post(f"/api/crm/leads/{lead.id}/convert?preview=true")

    assert response.status_code == 200
    assert response.json()["company_is_new"] is False
    assert repo.companies == {existing.id: existing}


def test_confirm_convert_persists_and_marks_lead_converted() -> None:
    """REQ-004: sem `preview` -> executa a conversão de verdade."""
    repo = _FakeCrmRepository()
    lead = _seed_lead(repo, company_name="Acme Ltda", email="joao@acme.com")
    client = _client(repo)

    response = client.post(f"/api/crm/leads/{lead.id}/convert")

    assert response.status_code == 200
    body = response.json()
    assert body["contact"]["name"] == "João"
    assert body["company"]["name"] == "Acme Ltda"
    assert body["deal"]["stage"] == "qualified"
    assert body["lead"]["converted_at"] is not None
    assert len(repo.contacts) == 1
    assert len(repo.companies) == 1
    assert len(repo.deals) == 1
    assert repo.leads[lead.id].converted_at is not None


def test_convert_missing_lead_returns_404() -> None:
    """Lead inexistente -> 404 tanto em preview quanto em confirm."""
    repo = _FakeCrmRepository()
    client = _client(repo)

    assert (
        client.post("/api/crm/leads/does-not-exist/convert?preview=true").status_code
        == 404
    )
    assert client.post("/api/crm/leads/does-not-exist/convert").status_code == 404
