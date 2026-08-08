"""Testes dos use cases de notas CRM (add-simple-crm-module-task-usecases-3).

Unit-1: create_note single target (REQ-001)
"""
from __future__ import annotations

import ast
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from src.application.ports.crm_repository import CrmRepositoryPort
from crm_repository_fakes import CrmRepositoryPortExtensions
from src.domain.crm import Company, Contact, Deal, DealStage, Note, NoteSource
from src.domain.shared.errors import DomainError


class _FakeCrmRepository(CrmRepositoryPortExtensions, CrmRepositoryPort):
    def __init__(self) -> None:
        self.companies: dict[str, Company] = {}
        self.contacts: dict[str, Contact] = {}
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
        self.notes.append(note)
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
            for n in self.notes
            if n.user_id == user_id and n.contact_id == contact_id
        ]
        return sorted(items, key=lambda n: n.created_at, reverse=True)

    async def list_notes_for_company(
        self,
        user_id: str,
        company_id: str,
        *,
        include_archived: bool = False,
    ) -> list[Note]:
        items = [
            n
            for n in self.notes
            if n.user_id == user_id and n.company_id == company_id
        ]
        return sorted(items, key=lambda n: n.created_at, reverse=True)

    async def list_notes_for_deal(
        self,
        user_id: str,
        deal_id: str,
        *,
        include_archived: bool = False,
    ) -> list[Note]:
        items = [
            n for n in self.notes if n.user_id == user_id and n.deal_id == deal_id
        ]
        return sorted(items, key=lambda n: n.created_at, reverse=True)


async def test_create_note_rejects_zero_or_multiple_targets() -> None:
    """unit-1 (REQ-001): 0 ou 2+ alvos → DomainError."""
    from src.application.use_cases.create_crm_note import CreateCrmNote

    repo = _FakeCrmRepository()
    uc = CreateCrmNote(repository=repo)

    with pytest.raises(DomainError, match="alvo"):
        await uc.execute(user_id="user-a", body="oi", source=NoteSource.USER)

    with pytest.raises(DomainError, match="alvo"):
        await uc.execute(
            user_id="user-a",
            body="oi",
            source=NoteSource.USER,
            contact_id="c1",
            company_id="co1",
        )

    assert repo.notes == []


async def test_create_note_with_own_contact_persists_source() -> None:
    """unit-1 (REQ-001): um contact_id próprio → persiste com source."""
    from src.application.use_cases.create_crm_contact import CreateCrmContact
    from src.application.use_cases.create_crm_note import CreateCrmNote

    repo = _FakeCrmRepository()
    contact = await CreateCrmContact(repository=repo).execute(
        user_id="user-a", name="Ana", email="a@x.com"
    )
    note = await CreateCrmNote(repository=repo).execute(
        user_id="user-a",
        body="Follow-up amanhã",
        source=NoteSource.AGENT,
        contact_id=contact.id,
    )
    assert note.id
    assert note.source == NoteSource.AGENT
    assert note.contact_id == contact.id
    assert note.company_id is None
    assert note.deal_id is None
    assert len(repo.notes) == 1


async def test_create_note_rejects_foreign_contact() -> None:
    """REQ-001: alvo de outro user falha."""
    from src.application.use_cases.create_crm_contact import CreateCrmContact
    from src.application.use_cases.create_crm_note import CreateCrmNote

    repo = _FakeCrmRepository()
    contact = await CreateCrmContact(repository=repo).execute(
        user_id="user-b", name="Ana", email="a@x.com"
    )
    with pytest.raises(DomainError):
        await CreateCrmNote(repository=repo).execute(
            user_id="user-a",
            body="hack",
            source=NoteSource.USER,
            contact_id=contact.id,
        )
    assert repo.notes == []


async def test_list_notes_for_contact_newest_first() -> None:
    """REQ-002: list ordenada mais recente primeiro."""
    from src.application.use_cases.create_crm_contact import CreateCrmContact
    from src.application.use_cases.create_crm_note import CreateCrmNote
    from src.application.use_cases.list_crm_notes import ListCrmNotes

    repo = _FakeCrmRepository()
    contact = await CreateCrmContact(repository=repo).execute(
        user_id="user-a", name="Ana", email="a@x.com"
    )
    older = await CreateCrmNote(repository=repo).execute(
        user_id="user-a",
        body="antiga",
        source=NoteSource.USER,
        contact_id=contact.id,
    )
    # força timestamps distintos no fake após create
    older.created_at = datetime.now(UTC) - timedelta(hours=1)
    newer = await CreateCrmNote(repository=repo).execute(
        user_id="user-a",
        body="nova",
        source=NoteSource.USER,
        contact_id=contact.id,
    )
    newer.created_at = datetime.now(UTC)

    listed = await ListCrmNotes(repository=repo).execute(
        user_id="user-a", contact_id=contact.id
    )
    assert [n.body for n in listed] == ["nova", "antiga"]


def test_no_update_crm_note_use_case_module() -> None:
    """REQ-003: não existe operação de update de body na aplicação."""
    use_cases_dir = (
        Path(__file__).parent.parent / "src" / "application" / "use_cases"
    )
    assert not (use_cases_dir / "update_crm_note.py").exists()
    for path in use_cases_dir.glob("crm_note*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                assert "Update" not in node.name
