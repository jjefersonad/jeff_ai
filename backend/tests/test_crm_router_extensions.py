"""Testes da API CRM estendida (crm-ext-task-api-1).

Unit-1: GET contacts envelope paginado
Unit-2: POST field-definitions 201 / 422 / 401
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

import src.infrastructure.web.crm_router as crm_router
from crm_repository_fakes import CrmRepositoryPortExtensions
from src.application.ports.crm_repository import CrmRepositoryPort
from src.domain.crm import (
    Company,
    Contact,
    Deal,
    DealStage,
    DuplicateFieldDefinitionError,
    FieldDefinition,
    FieldEntity,
    Note,
)
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
        self.definitions: dict[str, FieldDefinition] = {}

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
        items = [c for c in self.contacts.values() if c.user_id == user_id]
        if not include_archived:
            items = [c for c in items if c.archived_at is None]
        return items

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

    async def create_field_definition(
        self, definition: FieldDefinition
    ) -> FieldDefinition:
        for existing in self.definitions.values():
            if (
                existing.user_id == definition.user_id
                and existing.entity == definition.entity
                and existing.key == definition.key
            ):
                raise DuplicateFieldDefinitionError("duplicate")
        self.definitions[definition.id] = definition
        return definition

    async def list_field_definitions(
        self,
        user_id: str,
        *,
        entity: FieldEntity | None = None,
    ) -> list[FieldDefinition]:
        items = [d for d in self.definitions.values() if d.user_id == user_id]
        if entity is not None:
            items = [d for d in items if d.entity == entity]
        return items

    async def update_field_definition_label(
        self, user_id: str, definition_id: str, label: str
    ) -> FieldDefinition | None:
        definition = self.definitions.get(definition_id)
        if definition is None or definition.user_id != user_id:
            return None
        definition.label = label
        definition.updated_at = datetime.now(UTC)
        return definition


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


def test_get_contacts_returns_paginated_envelope(client: TestClient) -> None:
    """unit-1: GET /api/crm/contacts → {items,total,page,page_size}."""
    _as(client, _USER_A)
    for i in range(3):
        created = client.post(
            "/api/crm/contacts",
            json={"name": f"C{i}", "email": f"c{i}@x.com"},
        )
        assert created.status_code == 201

    response = client.get("/api/crm/contacts?page=1&page_size=2")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, dict)
    assert "items" in body
    assert body["total"] == 3
    assert body["page"] == 1
    assert body["page_size"] == 2
    assert len(body["items"]) == 2
    assert "city" in body["items"][0]
    assert "custom_values" in body["items"][0]


def test_post_field_definition_creates_and_rejects_duplicate(
    client: TestClient,
) -> None:
    """unit-2: POST definition → 201; duplicata → 422; sem auth → 401."""
    payload = {
        "entity": "contact",
        "key": "segmento",
        "label": "Segmento",
        "field_type": "text",
    }

    unauth = client.post("/api/crm/field-definitions", json=payload)
    assert unauth.status_code == 401

    _as(client, _USER_A)
    created = client.post("/api/crm/field-definitions", json=payload)
    assert created.status_code == 201
    body = created.json()
    assert body["id"]
    assert body["key"] == "segmento"
    assert body["entity"] == "contact"

    duplicate = client.post("/api/crm/field-definitions", json=payload)
    assert duplicate.status_code == 422


def test_post_contact_with_city_returns_location_fields(client: TestClient) -> None:
    """REQ-ADD-001: create contact devolve city/state/custom_values."""
    _as(client, _USER_A)
    response = client.post(
        "/api/crm/contacts",
        json={
            "name": "Ana",
            "email": "ana@x.com",
            "city": "São Paulo",
            "state": "SP",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["city"] == "São Paulo"
    assert body["state"] == "SP"
    assert body["custom_values"] == {}
