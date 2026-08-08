"""Testes extendidos de contact/list/archive (crm-ext-task-usecases-2)."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

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
    FieldType,
    Note,
    NoteSource,
)


class _FakeCrmRepository(CrmRepositoryPortExtensions, CrmRepositoryPort):
    def __init__(self) -> None:
        self.contacts: dict[str, Contact] = {}
        self.deals: dict[str, Deal] = {}
        self.notes: dict[str, Note] = {}
        self.definitions: dict[str, FieldDefinition] = {}

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
        items = [c for c in self.contacts.values() if c.user_id == user_id]
        if not include_archived:
            items = [c for c in items if c.archived_at is None]
        if company_id is not None:
            items = [c for c in items if c.company_id == company_id]
        if query:
            q = query.lower()
            items = [
                c
                for c in items
                if q in c.name.lower()
                or (c.email and q in c.email.lower())
                or (c.phone and q in c.phone.lower())
            ]
        return sorted(items, key=lambda c: c.updated_at, reverse=True)

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
        now = datetime.now(UTC)
        contact.archived_at = now
        contact.updated_at = now
        self.contacts[contact.id] = contact
        for deal in self.deals.values():
            if (
                deal.user_id == user_id
                and deal.contact_id == contact_id
                and deal.archived_at is None
            ):
                deal.archived_at = now
                deal.updated_at = now
        for note in self.notes.values():
            if (
                note.user_id == user_id
                and note.contact_id == contact_id
                and note.archived_at is None
            ):
                note.archived_at = now
        return contact

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
        return None

    async def archive_deal(self, user_id: str, deal_id: str) -> Deal | None:
        return None

    async def move_deal(
        self, user_id: str, deal_id: str, stage: DealStage
    ) -> Deal | None:
        return None

    async def create_note(self, note: Note) -> Note:
        self.notes[note.id] = note
        return note

    async def list_notes_for_contact(
        self,
        user_id: str,
        contact_id: str,
        *,
        include_archived: bool = False,
    ) -> list[Note]:
        items = [
            n
            for n in self.notes.values()
            if n.user_id == user_id and n.contact_id == contact_id
        ]
        if not include_archived:
            items = [n for n in items if n.archived_at is None]
        return items

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
        return None


async def test_create_contact_with_city_and_custom_values() -> None:
    """unit-1: CreateCrmContact com city/state/custom_values → get devolve."""
    from src.application.use_cases.create_crm_contact import CreateCrmContact
    from src.application.use_cases.create_crm_field_definition import (
        CreateCrmFieldDefinition,
    )
    from src.application.use_cases.get_crm_contact import GetCrmContact

    repo = _FakeCrmRepository()
    await CreateCrmFieldDefinition(repository=repo).execute(
        user_id="user-a",
        entity=FieldEntity.CONTACT,
        key="segmento",
        label="Segmento",
        field_type=FieldType.TEXT,
    )
    created = await CreateCrmContact(repository=repo).execute(
        user_id="user-a",
        name="Ana",
        email="ana@x.com",
        city="São Paulo",
        state="SP",
        custom_values={"segmento": "PME"},
    )
    got = await GetCrmContact(repository=repo).execute(
        user_id="user-a", contact_id=created.id
    )
    assert got is not None
    assert got.city == "São Paulo"
    assert got.state == "SP"
    assert got.custom_values == {"segmento": "PME"}


async def test_list_crm_contacts_returns_paginated_page() -> None:
    """unit-2: ListCrmContacts com page/page_size → PaginatedContacts."""
    from src.application.use_cases.create_crm_contact import CreateCrmContact
    from src.application.use_cases.list_crm_contacts import ListCrmContacts

    repo = _FakeCrmRepository()
    for i in range(5):
        await CreateCrmContact(repository=repo).execute(
            user_id="user-a",
            name=f"C{i}",
            email=f"c{i}@x.com",
        )

    page = await ListCrmContacts(repository=repo).execute(
        user_id="user-a", page=1, page_size=2
    )
    assert len(page.items) == 2
    assert page.total == 5
    assert page.page == 1
    assert page.page_size == 2


async def test_archive_crm_contact_cascades_linked_data() -> None:
    """unit-3: ArchiveCrmContact arquiva notes e deals vinculados."""
    from src.application.use_cases.archive_crm_contact import ArchiveCrmContact
    from src.application.use_cases.create_crm_contact import CreateCrmContact
    from src.application.use_cases.create_crm_deal import CreateCrmDeal
    from src.application.use_cases.create_crm_note import CreateCrmNote
    from src.application.use_cases.list_crm_deals import ListCrmDeals

    repo = _FakeCrmRepository()
    contact = await CreateCrmContact(repository=repo).execute(
        user_id="user-a", name="Ana", email="a@x.com"
    )
    deal = await CreateCrmDeal(repository=repo).execute(
        user_id="user-a", title="Opp", contact_id=contact.id
    )
    await CreateCrmNote(repository=repo).execute(
        user_id="user-a",
        body="hi",
        source=NoteSource.USER,
        contact_id=contact.id,
    )

    archived = await ArchiveCrmContact(repository=repo).execute(
        user_id="user-a", contact_id=contact.id
    )
    assert archived is not None
    assert archived.archived_at is not None

    assert await ListCrmDeals(repository=repo).execute(user_id="user-a") == []
    notes = await repo.list_notes_for_contact("user-a", contact.id)
    assert notes == []
    deals_archived = await ListCrmDeals(repository=repo).execute(
        user_id="user-a", include_archived=True
    )
    assert any(d.id == deal.id and d.archived_at is not None for d in deals_archived)
