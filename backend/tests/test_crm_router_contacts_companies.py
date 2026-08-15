"""Testes de `/api/crm` contacts/companies (add-simple-crm-module-task-api-1).

Unit-1: POST contacts 201 / 422
Unit-2: GET foreign company 404
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

import src.infrastructure.web.crm_router as crm_router
import src.infrastructure.web.webapp as webapp
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
_USER_B = User(
    id="user-b",
    username="bob",
    password_hash="h",
    role="user",
    is_active=True,
    created_at=datetime(2026, 1, 1, tzinfo=UTC),
)


class _FakeCrmRepository(CrmRepositoryPortExtensions, CrmRepositoryPort):
    def __init__(self) -> None:
        self.companies: dict[str, Company] = {}
        self.contacts: dict[str, Contact] = {}

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
        items = [c for c in self.companies.values() if c.user_id == user_id]
        if not include_archived:
            items = [c for c in items if c.archived_at is None]
        return items

    async def update_company(self, company: Company) -> Company | None:
        existing = self.companies.get(company.id)
        if existing is None or existing.user_id != company.user_id:
            return None
        self.companies[company.id] = company
        return company

    async def archive_company(self, user_id: str, company_id: str) -> Company | None:
        company = await self.get_company(user_id, company_id)
        if company is None:
            return None
        company.archived_at = datetime.now(UTC)
        self.companies[company.id] = company
        return company

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
        items = [c for c in self.contacts.values() if c.user_id == user_id]
        if not include_archived:
            items = [c for c in items if c.archived_at is None]
        return items

    async def update_contact(self, contact: Contact) -> Contact | None:
        existing = self.contacts.get(contact.id)
        if existing is None or existing.user_id != contact.user_id:
            return None
        self.contacts[contact.id] = contact
        return contact

    async def archive_contact(self, user_id: str, contact_id: str) -> Contact | None:
        contact = await self.get_contact(user_id, contact_id)
        if contact is None:
            return None
        contact.archived_at = datetime.now(UTC)
        self.contacts[contact.id] = contact
        return contact

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


@pytest.fixture
def repo() -> _FakeCrmRepository:
    return _FakeCrmRepository()


@pytest.fixture
def client(repo: _FakeCrmRepository):
    app = FastAPI(dependencies=[Depends(require_auth)])
    app.include_router(crm_router.router)
    app.dependency_overrides[crm_router._crm_repository] = lambda: repo
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _as(client: TestClient, user: User) -> None:
    client.app.dependency_overrides[require_auth] = lambda: user


def test_post_contact_valid_returns_201(client: TestClient) -> None:
    """unit-1: POST contact válido → 201 com id."""
    _as(client, _USER_A)
    response = client.post(
        "/api/crm/contacts",
        json={"name": "Ana", "email": "ana@example.com"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["id"]
    assert body["user_id"] == "user-a"
    assert body["email"] == "ana@example.com"


def test_post_contact_omits_whatsapp_opt_in_defaults_false(
    client: TestClient,
) -> None:
    """REQ-006: POST sem o campo persiste false; GET/list devolve o valor."""
    _as(client, _USER_A)
    created = client.post(
        "/api/crm/contacts",
        json={"name": "Ana", "email": "ana@example.com"},
    )
    assert created.status_code == 201
    body = created.json()
    assert body["whatsapp_opt_in"] is False
    contact_id = body["id"]

    listed = client.get("/api/crm/contacts")
    assert listed.status_code == 200
    items = listed.json()["items"]
    assert items[0]["id"] == contact_id
    assert items[0]["whatsapp_opt_in"] is False

    got = client.get(f"/api/crm/contacts/{contact_id}")
    assert got.status_code == 200
    assert got.json()["whatsapp_opt_in"] is False


def test_post_contact_whatsapp_opt_in_true_persists(client: TestClient) -> None:
    """REQ-006: POST com whatsapp_opt_in=true persiste true."""
    _as(client, _USER_A)
    created = client.post(
        "/api/crm/contacts",
        json={
            "name": "Ana",
            "email": "ana@example.com",
            "whatsapp_opt_in": True,
        },
    )
    assert created.status_code == 201
    assert created.json()["whatsapp_opt_in"] is True

    listed = client.get("/api/crm/contacts")
    assert listed.json()["items"][0]["whatsapp_opt_in"] is True


def test_patch_contact_whatsapp_opt_in_true(client: TestClient) -> None:
    """REQ-006: PATCH com whatsapp_opt_in=true altera de false para true."""
    _as(client, _USER_A)
    created = client.post(
        "/api/crm/contacts",
        json={"name": "Ana", "email": "ana@example.com"},
    )
    assert created.json()["whatsapp_opt_in"] is False
    contact_id = created.json()["id"]

    patched = client.patch(
        f"/api/crm/contacts/{contact_id}",
        json={"whatsapp_opt_in": True},
    )
    assert patched.status_code == 200
    assert patched.json()["whatsapp_opt_in"] is True

    got = client.get(f"/api/crm/contacts/{contact_id}")
    assert got.json()["whatsapp_opt_in"] is True


def test_patch_contact_omits_whatsapp_opt_in_preserves(client: TestClient) -> None:
    """REQ-006: PATCH sem o campo não altera o valor persistido."""
    _as(client, _USER_A)
    created = client.post(
        "/api/crm/contacts",
        json={
            "name": "Ana",
            "email": "ana@example.com",
            "whatsapp_opt_in": True,
        },
    )
    contact_id = created.json()["id"]

    patched = client.patch(
        f"/api/crm/contacts/{contact_id}",
        json={"phone": "+5511999999999"},
    )
    assert patched.status_code == 200
    assert patched.json()["phone"] == "+5511999999999"
    assert patched.json()["whatsapp_opt_in"] is True


def test_patch_contact_whatsapp_opt_in_foreign_returns_404(
    client: TestClient,
) -> None:
    """REQ-006: PATCH opt-in de outro user → 404; o bit do dono não muda."""
    _as(client, _USER_A)
    created = client.post(
        "/api/crm/contacts",
        json={"name": "Ana", "email": "ana@example.com"},
    )
    contact_id = created.json()["id"]

    _as(client, _USER_B)
    patched = client.patch(
        f"/api/crm/contacts/{contact_id}",
        json={"whatsapp_opt_in": True},
    )
    assert patched.status_code == 404

    _as(client, _USER_A)
    got = client.get(f"/api/crm/contacts/{contact_id}")
    assert got.status_code == 200
    assert got.json()["whatsapp_opt_in"] is False


def test_post_contact_without_identifier_returns_422(client: TestClient) -> None:
    """unit-1: sem email/phone → 422."""
    _as(client, _USER_A)
    response = client.post("/api/crm/contacts", json={"name": "Só Nome"})
    assert response.status_code == 422


def test_get_foreign_company_returns_404(
    client: TestClient, repo: _FakeCrmRepository
) -> None:
    """unit-2: GET company de outro user → 404."""
    _as(client, _USER_B)
    created = client.post("/api/crm/companies", json={"name": "Empresa B"})
    assert created.status_code == 201
    company_id = created.json()["id"]

    _as(client, _USER_A)
    response = client.get(f"/api/crm/companies/{company_id}")
    assert response.status_code == 404


def test_webapp_includes_crm_router() -> None:
    """Design: crm_router montado no webapp."""
    paths = {getattr(route, "path", "") for route in webapp.app.routes}
    assert "/api/crm/contacts" in paths
    assert "/api/crm/companies" in paths
    assert "/api/crm/field-definitions" in paths
