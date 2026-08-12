"""Testes de `/api/crm/leads` (sales-pipeline-via-agent-task-backend-leads-1).

Unit-1: POST /api/crm/leads com name+phone -> 201
Unit-2: POST /api/crm/leads sem email/phone/company_name -> 4xx, não persiste
"""
from __future__ import annotations

from datetime import UTC, datetime

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

import src.infrastructure.web.crm_router as crm_router
from src.application.ports.crm_repository import CrmRepositoryPort
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
        items = [
            lead for lead in self.leads.values() if lead.user_id == user_id
        ]
        if converted:
            return [lead for lead in items if lead.converted_at is not None]
        return [lead for lead in items if lead.converted_at is None]


def _client(repo: _FakeCrmRepository) -> TestClient:
    app = FastAPI(dependencies=[Depends(require_auth)])
    app.include_router(crm_router.router)
    app.dependency_overrides[crm_router._crm_repository] = lambda: repo
    app.dependency_overrides[require_auth] = lambda: _USER_A
    return TestClient(app)


def test_post_lead_with_name_and_phone_returns_201() -> None:
    """unit-1 (REQ-001): name+phone apenas -> 201 com campos do lead criado."""
    client = _client(_FakeCrmRepository())
    response = client.post(
        "/api/crm/leads", json={"name": "João Lead", "phone": "11999998888"}
    )
    assert response.status_code == 201
    body = response.json()
    assert body["id"]
    assert body["name"] == "João Lead"
    assert body["phone"] == "11999998888"
    assert body["status"] == "new"


def test_post_lead_without_any_contact_field_rejected() -> None:
    """unit-2 (REQ-001): sem email/phone/company_name -> 4xx, não persiste."""
    repo = _FakeCrmRepository()
    client = _client(repo)
    response = client.post("/api/crm/leads", json={"name": "Sem Contato"})
    assert 400 <= response.status_code < 500
    assert repo.leads == {}


def test_list_leads_returns_only_active_by_default_and_converted_with_flag() -> None:
    """REQ-002: lista ativos por default; `converted=true` mostra convertidos."""
    repo = _FakeCrmRepository()
    client = _client(repo)

    active = client.post(
        "/api/crm/leads", json={"name": "Ativo", "phone": "111"}
    ).json()
    converted = client.post(
        "/api/crm/leads", json={"name": "Convertido", "phone": "222"}
    ).json()
    repo.leads[converted["id"]].converted_at = datetime.now(UTC)

    default_list = client.get("/api/crm/leads").json()
    assert [item["id"] for item in default_list] == [active["id"]]

    converted_list = client.get("/api/crm/leads?converted=true").json()
    assert [item["id"] for item in converted_list] == [converted["id"]]
