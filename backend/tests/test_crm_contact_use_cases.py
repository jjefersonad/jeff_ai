"""Testes dos use cases de contatos CRM (add-simple-crm-module-task-usecases-1).

Unit-1: create rejeita sem email/phone
Unit-2: create happy path com name+email
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.application.ports.crm_repository import CrmRepositoryPort
from src.domain.crm import Company, Contact, Deal, DealStage, Note
from src.domain.shared.errors import DomainError


class _FakeCrmRepository(CrmRepositoryPort):
    def __init__(self) -> None:
        self.contacts: dict[str, Contact] = {}
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
        self.create_calls += 1
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
        contact.updated_at = datetime.now(UTC)
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
        self, user_id: str, contact_id: str
    ) -> list[Note]:
        return []

    async def list_notes_for_company(
        self, user_id: str, company_id: str
    ) -> list[Note]:
        return []

    async def list_notes_for_deal(self, user_id: str, deal_id: str) -> list[Note]:
        return []


async def test_create_contact_rejects_missing_identifier() -> None:
    """unit-1 (REQ-001): name sem email/phone → DomainError e não persiste."""
    from src.application.use_cases.create_crm_contact import CreateCrmContact

    repo = _FakeCrmRepository()
    uc = CreateCrmContact(repository=repo)

    with pytest.raises(DomainError, match="email|phone"):
        await uc.execute(user_id="user-a", name="Só Nome")

    assert repo.create_calls == 0
    assert repo.contacts == {}


async def test_create_contact_happy_path() -> None:
    """unit-2 (REQ-001): name+email → contato com id e user_id."""
    from src.application.use_cases.create_crm_contact import CreateCrmContact

    repo = _FakeCrmRepository()
    uc = CreateCrmContact(repository=repo)

    contact = await uc.execute(
        user_id="user-a",
        name="Ana Silva",
        email="ana@example.com",
    )

    assert contact.id
    assert contact.user_id == "user-a"
    assert contact.name == "Ana Silva"
    assert contact.email == "ana@example.com"
    assert repo.create_calls == 1
    assert repo.contacts[contact.id].user_id == "user-a"


async def test_update_contact_bumps_updated_at() -> None:
    """REQ-003: update mutável atualiza updated_at."""
    from src.application.use_cases.create_crm_contact import CreateCrmContact
    from src.application.use_cases.update_crm_contact import UpdateCrmContact

    repo = _FakeCrmRepository()
    created = await CreateCrmContact(repository=repo).execute(
        user_id="user-a", name="Ana", email="a@x.com"
    )
    before = created.updated_at

    updated = await UpdateCrmContact(repository=repo).execute(
        user_id="user-a",
        contact_id=created.id,
        phone="+5511999999999",
    )
    assert updated is not None
    assert updated.phone == "+5511999999999"
    assert updated.updated_at >= before


async def test_archive_hides_from_default_list() -> None:
    """REQ-004: archive oculta da listagem padrão."""
    from src.application.use_cases.archive_crm_contact import ArchiveCrmContact
    from src.application.use_cases.create_crm_contact import CreateCrmContact
    from src.application.use_cases.list_crm_contacts import ListCrmContacts

    repo = _FakeCrmRepository()
    created = await CreateCrmContact(repository=repo).execute(
        user_id="user-a", name="Ana", email="a@x.com"
    )
    await ArchiveCrmContact(repository=repo).execute(
        user_id="user-a", contact_id=created.id
    )

    listed = await ListCrmContacts(repository=repo).execute(user_id="user-a")
    assert all(c.id != created.id for c in listed)

    with_archived = await ListCrmContacts(repository=repo).execute(
        user_id="user-a", include_archived=True
    )
    assert any(c.id == created.id for c in with_archived)


async def test_get_contact_cross_user_returns_none() -> None:
    """REQ-005: operação cross-user → not found (None)."""
    from src.application.use_cases.create_crm_contact import CreateCrmContact
    from src.application.use_cases.get_crm_contact import GetCrmContact

    repo = _FakeCrmRepository()
    created = await CreateCrmContact(repository=repo).execute(
        user_id="user-a", name="Ana", email="a@x.com"
    )

    assert await GetCrmContact(repository=repo).execute(
        user_id="user-b", contact_id=created.id
    ) is None
