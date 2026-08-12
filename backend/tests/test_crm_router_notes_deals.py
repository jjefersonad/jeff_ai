"""Testes de `/api/crm` notes/deals/stages (add-simple-crm-module-task-api-2).

Unit-1: GET deals/stages
Unit-2: PATCH notes unsupported
"""
from __future__ import annotations

from datetime import UTC, datetime

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

import src.infrastructure.web.crm_router as crm_router
from src.application.ports.crm_repository import CrmRepositoryPort
from crm_repository_fakes import CrmRepositoryPortExtensions
from src.domain.crm import Company, Contact, Deal, DealStage, Note
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
        self.companies: dict[str, Company] = {}
        self.contacts: dict[str, Contact] = {}
        self.deals: dict[str, Deal] = {}
        self.notes: list[Note] = []

    async def create_company(self, company: Company) -> Company:
        self.companies[company.id] = company
        return company

    async def get_company(self, user_id: str, company_id: str) -> Company | None:
        company = self.companies.get(company_id)
        if company is None or company.user_id != user_id:
            return None
        return company

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
        self.contacts[contact.id] = contact
        return contact

    async def get_contact(self, user_id: str, contact_id: str) -> Contact | None:
        contact = self.contacts.get(contact_id)
        if contact is None or contact.user_id != user_id:
            return None
        return contact

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
        self.deals[deal.id] = deal
        return deal

    async def get_deal(self, user_id: str, deal_id: str) -> Deal | None:
        deal = self.deals.get(deal_id)
        if deal is None or deal.user_id != user_id:
            return None
        return deal

    async def list_deals(
        self,
        user_id: str,
        *,
        stage: DealStage | None = None,
        include_archived: bool = False,
    ) -> list[Deal]:
        items = [d for d in self.deals.values() if d.user_id == user_id]
        if not include_archived:
            items = [d for d in items if d.archived_at is None]
        if stage is not None:
            items = [d for d in items if d.stage == stage]
        return items

    async def update_deal(self, deal: Deal) -> Deal | None:
        existing = self.deals.get(deal.id)
        if existing is None or existing.user_id != deal.user_id:
            return None
        self.deals[deal.id] = deal
        return deal

    async def archive_deal(self, user_id: str, deal_id: str) -> Deal | None:
        deal = await self.get_deal(user_id, deal_id)
        if deal is None:
            return None
        deal.archived_at = datetime.now(UTC)
        self.deals[deal.id] = deal
        return deal

    async def move_deal(
        self, user_id: str, deal_id: str, stage: DealStage
    ) -> Deal | None:
        deal = await self.get_deal(user_id, deal_id)
        if deal is None:
            return None
        deal.stage = stage
        self.deals[deal.id] = deal
        return deal

    async def create_note(self, note: Note) -> Note:
        self.notes.append(note)
        return note

    async def list_notes_for_contact(
        self,
        user_id: str,
        contact_id: str,
        *,
        include_archived: bool = False,
    ) -> list[Note]:
        return [
            n
            for n in self.notes
            if n.user_id == user_id and n.contact_id == contact_id
        ]

    async def list_notes_for_company(
        self,
        user_id: str,
        company_id: str,
        *,
        include_archived: bool = False,
    ) -> list[Note]:
        return [
            n
            for n in self.notes
            if n.user_id == user_id and n.company_id == company_id
        ]

    async def list_notes_for_deal(
        self,
        user_id: str,
        deal_id: str,
        *,
        include_archived: bool = False,
    ) -> list[Note]:
        return [
            n for n in self.notes if n.user_id == user_id and n.deal_id == deal_id
        ]


def _client(repo: _FakeCrmRepository) -> TestClient:
    app = FastAPI(dependencies=[Depends(require_auth)])
    app.include_router(crm_router.router)
    app.dependency_overrides[crm_router._crm_repository] = lambda: repo
    app.dependency_overrides[require_auth] = lambda: _USER_A
    return TestClient(app)


def test_get_deal_stages_returns_five_ordered() -> None:
    """unit-1: GET /api/crm/deals/stages → 200 com 5 estágios."""
    client = _client(_FakeCrmRepository())
    response = client.get("/api/crm/deals/stages")
    assert response.status_code == 200
    assert response.json() == [
        "qualified",
        "proposal",
        "negotiation",
        "won",
        "lost",
    ]


def test_patch_note_unsupported() -> None:
    """unit-2: PATCH /api/crm/notes/{id} → 405 ou 404."""
    client = _client(_FakeCrmRepository())
    response = client.patch("/api/crm/notes/any-id", json={"body": "x"})
    assert response.status_code in {404, 405}


def test_create_deal_and_move() -> None:
    """REQ deals: create default qualified + move."""
    client = _client(_FakeCrmRepository())
    created = client.post("/api/crm/deals", json={"title": "Deal Acme"})
    assert created.status_code == 201
    body = created.json()
    assert body["stage"] == "qualified"
    deal_id = body["id"]

    moved = client.post(f"/api/crm/deals/{deal_id}/move", json={"stage": "won"})
    assert moved.status_code == 200
    assert moved.json()["stage"] == "won"


def test_create_note_on_contact() -> None:
    """REQ notes: POST note em contato."""
    repo = _FakeCrmRepository()
    client = _client(repo)
    contact = client.post(
        "/api/crm/contacts", json={"name": "Ana", "email": "a@x.com"}
    )
    contact_id = contact.json()["id"]
    note = client.post(
        "/api/crm/notes",
        json={"body": "Follow-up", "contact_id": contact_id, "source": "user"},
    )
    assert note.status_code == 201
    assert note.json()["source"] == "user"
    assert note.json()["contact_id"] == contact_id
