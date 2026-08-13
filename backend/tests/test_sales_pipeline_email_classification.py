"""Testes de `ClassifyEmailByContact` (sales-pipeline-via-agent-task-backend-email-1).

Unit-1 (REQ-005): contato com deal ativo -> cria nota `source='system'` no
deal, sem mudar o estágio do deal.
Unit-2 (REQ-005): contato sem deal ativo -> nenhuma nota é criada.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from crm_repository_fakes import CrmRepositoryPortExtensions

from src.application.ports.crm_repository import CrmRepositoryPort
from src.application.use_cases.classify_email_by_contact import (
    ClassifyEmailByContact,
)
from src.domain.crm import Company, Contact, Deal, DealStage, Note, NoteSource


class _FakeCrmRepository(CrmRepositoryPortExtensions, CrmRepositoryPort):
    def __init__(self) -> None:
        self.contacts: dict[str, Contact] = {}
        self.active_deals_by_contact: dict[str, Deal] = {}
        self.notes: list[Note] = []

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

    async def get_contact_by_email(
        self, user_id: str, email: str
    ) -> Contact | None:
        target = email.strip().lower()
        for contact in self.contacts.values():
            if contact.user_id != user_id:
                continue
            if contact.email and contact.email.strip().lower() == target:
                return contact
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

    async def get_active_deal_by_contact(
        self, user_id: str, contact_id: str
    ) -> Deal | None:
        deal = self.active_deals_by_contact.get(contact_id)
        if deal is None or deal.user_id != user_id:
            return None
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


def _contact(*, user_id: str = "user-a", email: str = "joao@acme.com") -> Contact:
    now = datetime.now(UTC)
    return Contact(
        id=str(uuid.uuid4()),
        user_id=user_id,
        name="João",
        email=email,
        created_at=now,
        updated_at=now,
    )


def _deal(*, user_id: str, stage: DealStage = DealStage.QUALIFIED) -> Deal:
    now = datetime.now(UTC)
    return Deal(
        id=str(uuid.uuid4()),
        user_id=user_id,
        title="Acme",
        stage=stage,
        created_at=now,
        updated_at=now,
    )


async def test_classify_by_contact_with_active_deal_writes_system_note() -> None:
    """unit-1 (REQ-005): contato com deal ativo -> nota `source='system'`
    no deal; o estágio do deal não muda."""
    repo = _FakeCrmRepository()
    contact = _contact()
    deal = _deal(user_id=contact.user_id)
    repo.contacts[contact.id] = contact
    repo.active_deals_by_contact[contact.id] = deal

    use_case = ClassifyEmailByContact(repository=repo)
    note = await use_case.execute(
        user_id=contact.user_id, sender_email=contact.email, subject="Proposta"
    )

    assert note is not None
    assert note.source == NoteSource.SYSTEM
    assert note.deal_id == deal.id
    assert note.body == "Email recebido: Proposta"
    assert len(repo.notes) == 1
    assert deal.stage == DealStage.QUALIFIED


async def test_classify_by_contact_without_active_deal_creates_no_note() -> None:
    """unit-2 (REQ-005): contato sem deal ativo -> nenhuma nota é criada."""
    repo = _FakeCrmRepository()
    contact = _contact()
    repo.contacts[contact.id] = contact
    # sem entrada em active_deals_by_contact -> sem deal ativo

    use_case = ClassifyEmailByContact(repository=repo)
    note = await use_case.execute(
        user_id=contact.user_id, sender_email=contact.email, subject="Oi"
    )

    assert note is None
    assert repo.notes == []
