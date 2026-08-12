"""Testes dos use cases de empresas CRM (add-simple-crm-module-task-usecases-2).

Unit-1: link contact rejects foreign company (REQ-004)
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.application.ports.crm_repository import CrmRepositoryPort
from crm_repository_fakes import CrmRepositoryPortExtensions
from src.domain.crm import Company, Contact, Deal, DealStage, Note
from src.domain.shared.errors import DomainError


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
        if query:
            q = query.lower()
            items = [
                c
                for c in items
                if q in c.name.lower() or (c.domain and q in c.domain.lower())
            ]
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
        company.updated_at = datetime.now(UTC)
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
        if company_id is not None:
            items = [c for c in items if c.company_id == company_id]
        return items

    async def update_contact(self, contact: Contact) -> Contact | None:
        existing = self.contacts.get(contact.id)
        if existing is None or existing.user_id != contact.user_id:
            return None
        self.contacts[contact.id] = contact
        return contact

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


async def test_link_contact_rejects_foreign_company() -> None:
    """unit-1 (REQ-004): company_id de outro user → DomainError; contato intacto."""
    from src.application.use_cases.create_crm_company import CreateCrmCompany
    from src.application.use_cases.create_crm_contact import CreateCrmContact
    from src.application.use_cases.update_crm_contact import UpdateCrmContact

    repo = _FakeCrmRepository()
    foreign = await CreateCrmCompany(repository=repo).execute(
        user_id="user-b", name="Empresa B"
    )
    contact = await CreateCrmContact(repository=repo).execute(
        user_id="user-a", name="Ana", email="a@x.com"
    )

    with pytest.raises(DomainError, match="company_id"):
        await UpdateCrmContact(repository=repo).execute(
            user_id="user-a",
            contact_id=contact.id,
            company_id=foreign.id,
        )

    stored = await repo.get_contact("user-a", contact.id)
    assert stored is not None
    assert stored.company_id is None


async def test_create_company_requires_name() -> None:
    """REQ-001: create sem name falha."""
    from src.application.use_cases.create_crm_company import CreateCrmCompany

    repo = _FakeCrmRepository()
    with pytest.raises(DomainError, match="name"):
        await CreateCrmCompany(repository=repo).execute(user_id="user-a", name="  ")


async def test_create_company_happy_path() -> None:
    """REQ-001: create com name ok."""
    from src.application.use_cases.create_crm_company import CreateCrmCompany

    repo = _FakeCrmRepository()
    company = await CreateCrmCompany(repository=repo).execute(
        user_id="user-a", name="Acme", website="https://acme.test"
    )
    assert company.id
    assert company.user_id == "user-a"
    assert company.name == "Acme"


async def test_link_contact_to_own_company() -> None:
    """REQ-004: vincular contato próprio a empresa própria."""
    from src.application.use_cases.create_crm_company import CreateCrmCompany
    from src.application.use_cases.create_crm_contact import CreateCrmContact
    from src.application.use_cases.list_crm_contacts import ListCrmContacts
    from src.application.use_cases.update_crm_contact import UpdateCrmContact

    repo = _FakeCrmRepository()
    company = await CreateCrmCompany(repository=repo).execute(
        user_id="user-a", name="Acme"
    )
    contact = await CreateCrmContact(repository=repo).execute(
        user_id="user-a", name="Ana", email="a@x.com"
    )
    updated = await UpdateCrmContact(repository=repo).execute(
        user_id="user-a",
        contact_id=contact.id,
        company_id=company.id,
    )
    assert updated is not None
    assert updated.company_id == company.id

    linked = await ListCrmContacts(repository=repo).execute(
        user_id="user-a", company_id=company.id
    )
    assert [c.id for c in linked.items] == [contact.id]


async def test_get_company_cross_user_returns_none() -> None:
    """REQ-005: get cross-user → not found."""
    from src.application.use_cases.create_crm_company import CreateCrmCompany
    from src.application.use_cases.get_crm_company import GetCrmCompany

    repo = _FakeCrmRepository()
    company = await CreateCrmCompany(repository=repo).execute(
        user_id="user-a", name="Acme"
    )
    assert (
        await GetCrmCompany(repository=repo).execute(
            user_id="user-b", company_id=company.id
        )
        is None
    )


async def test_update_company_preserves_source_lead_id() -> None:
    """REQ-003 (sales-pipeline-via-agent): update não apaga a origem via lead."""
    from src.application.use_cases.update_crm_company import UpdateCrmCompany

    repo = _FakeCrmRepository()
    company = Company(
        id="company-1",
        user_id="user-a",
        name="Acme",
        source_lead_id="lead-1",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    repo.companies[company.id] = company

    updated = await UpdateCrmCompany(repository=repo).execute(
        user_id="user-a", company_id=company.id, website="https://acme.test"
    )
    assert updated is not None
    assert updated.source_lead_id == "lead-1"


async def test_archive_company_hides_from_default_list() -> None:
    """REQ-002/003: archive soft-delete."""
    from src.application.use_cases.archive_crm_company import ArchiveCrmCompany
    from src.application.use_cases.create_crm_company import CreateCrmCompany
    from src.application.use_cases.list_crm_companies import ListCrmCompanies

    repo = _FakeCrmRepository()
    company = await CreateCrmCompany(repository=repo).execute(
        user_id="user-a", name="Acme"
    )
    await ArchiveCrmCompany(repository=repo).execute(
        user_id="user-a", company_id=company.id
    )
    listed = await ListCrmCompanies(repository=repo).execute(user_id="user-a")
    assert all(c.id != company.id for c in listed)
    with_archived = await ListCrmCompanies(repository=repo).execute(
        user_id="user-a", include_archived=True
    )
    assert any(c.id == company.id for c in with_archived)
