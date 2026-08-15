"""Testes das tools CRM estendidas (crm-ext-task-tools-1).

Unit-1: crm_create_field_definition sem identidade → erro, não persiste
Unit-2: crm_upsert_contact ignora user_id alienígena e grava city/custom_values
"""
from __future__ import annotations

import pytest

import src.tools.crm_tools as ct
from crm_repository_fakes import CrmRepositoryPortExtensions
from src.application.ports.crm_repository import CrmRepositoryPort
from src.application.use_cases.create_crm_contact import CreateCrmContact
from src.application.use_cases.create_crm_field_definition import (
    CreateCrmFieldDefinition,
)
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


class _FakeCrmRepository(CrmRepositoryPortExtensions, CrmRepositoryPort):
    def __init__(self) -> None:
        self.contacts: dict[str, Contact] = {}
        self.definitions: dict[str, FieldDefinition] = {}
        self.create_definition_calls = 0

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
        return [c for c in self.contacts.values() if c.user_id == user_id]

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
        self.create_definition_calls += 1
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
        return None


def _stub_resolved_user_id(
    monkeypatch: pytest.MonkeyPatch, user_id: str | None
) -> None:
    async def _fake_resolve_user_id() -> str | None:
        return user_id

    monkeypatch.setattr(ct, "resolve_user_id", _fake_resolve_user_id)


async def test_crm_create_field_definition_without_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """unit-1: sem user_id resolvível → erro; não persiste definição."""
    _stub_resolved_user_id(monkeypatch, None)
    repo = _FakeCrmRepository()
    monkeypatch.setattr(
        ct,
        "build_create_crm_field_definition",
        lambda: CreateCrmFieldDefinition(repository=repo),
    )

    result = await ct.crm_create_field_definition.ainvoke(
        {
            "entity": "contact",
            "key": "segmento",
            "label": "Segmento",
            "field_type": "text",
        }
    )

    assert isinstance(result, dict)
    assert "error" in result
    assert repo.create_definition_calls == 0
    assert repo.definitions == {}


async def test_crm_upsert_contact_ignores_alien_user_id_and_saves_extensions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """unit-2: user_id alienígena ignorado; city/custom_values gravados."""
    session_user = "user-a"
    _stub_resolved_user_id(monkeypatch, session_user)
    repo = _FakeCrmRepository()
    monkeypatch.setattr(
        ct, "build_create_crm_contact", lambda: CreateCrmContact(repository=repo)
    )
    monkeypatch.setattr(
        ct,
        "build_create_crm_field_definition",
        lambda: CreateCrmFieldDefinition(repository=repo),
    )

    await ct.crm_create_field_definition.ainvoke(
        {
            "entity": "contact",
            "key": "segmento",
            "label": "Segmento",
            "field_type": "text",
            "user_id": "user-alien",
        }
    )

    created = await ct.crm_upsert_contact.ainvoke(
        {
            "name": "Ana",
            "email": "ana@example.com",
            "city": "Curitiba",
            "state": "PR",
            "custom_values": {"segmento": "PME"},
            "user_id": "user-alien",
        }
    )
    assert created["user_id"] == session_user
    assert created["city"] == "Curitiba"
    assert created["state"] == "PR"
    assert created["custom_values"] == {"segmento": "PME"}
    assert created["whatsapp_opt_in"] is False
    assert "user-alien" not in {c.user_id for c in repo.contacts.values()}
    assert all(d.user_id == session_user for d in repo.definitions.values())
