"""Testes de `src/tools/crm_tools.py` (add-simple-crm-module-task-tools-1).

Unit-1 (REQ-003): sem identidade resolvível → erro e não consulta o repositório.
Unit-2 (REQ-003): `user_id` no payload do modelo é ignorado; usa só a sessão.
"""
from __future__ import annotations

import pytest

import src.tools.crm_tools as ct
from src.application.ports.crm_repository import CrmRepositoryPort
from crm_repository_fakes import CrmRepositoryPortExtensions
from src.application.use_cases.create_crm_contact import CreateCrmContact
from src.application.use_cases.create_crm_note import CreateCrmNote
from src.application.use_cases.list_crm_contacts import ListCrmContacts
from src.domain.crm import Company, Contact, Deal, DealStage, Note, NoteSource


class _FakeCrmRepository(CrmRepositoryPortExtensions, CrmRepositoryPort):
    def __init__(self) -> None:
        self.contacts: dict[str, Contact] = {}
        self.deals: dict[str, Deal] = {}
        self.notes: dict[str, Note] = {}
        self.list_contacts_calls: list[str] = []

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
        self.list_contacts_calls.append(user_id)
        return [c for c in self.contacts.values() if c.user_id == user_id]

    async def update_contact(self, contact: Contact) -> Contact | None:
        existing = self.contacts.get(contact.id)
        if existing is None or existing.user_id != contact.user_id:
            return None
        self.contacts[contact.id] = contact
        return contact

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
        return []

    async def update_deal(self, deal: Deal) -> Deal | None:
        return None

    async def archive_deal(self, user_id: str, deal_id: str) -> Deal | None:
        return None

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
        self.notes[note.id] = note
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


def _stub_resolved_user_id(
    monkeypatch: pytest.MonkeyPatch, user_id: str | None
) -> None:
    async def _fake_resolve_user_id() -> str | None:
        return user_id

    monkeypatch.setattr(ct, "resolve_user_id", _fake_resolve_user_id)


async def test_crm_search_contacts_without_identity_does_not_query_repo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """unit-1 (REQ-003): sem user_id resolvível → erro; repo não é consultado."""
    _stub_resolved_user_id(monkeypatch, None)
    repo = _FakeCrmRepository()
    monkeypatch.setattr(
        ct, "build_list_crm_contacts", lambda: ListCrmContacts(repository=repo)
    )

    result = await ct.crm_search_contacts.ainvoke({"query": "Ana"})

    assert isinstance(result, dict)
    assert "error" in result
    assert repo.list_contacts_calls == []


async def test_crm_tool_ignores_model_user_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """unit-2 (REQ-003): user_id alienígena no payload → operação usa só a sessão."""
    session_user = "user-a"
    _stub_resolved_user_id(monkeypatch, session_user)
    repo = _FakeCrmRepository()
    monkeypatch.setattr(
        ct, "build_create_crm_contact", lambda: CreateCrmContact(repository=repo)
    )
    monkeypatch.setattr(
        ct, "build_create_crm_note", lambda: CreateCrmNote(repository=repo)
    )

    created = await ct.crm_upsert_contact.ainvoke(
        {
            "name": "Ana",
            "email": "ana@example.com",
            "user_id": "user-alien",
        }
    )
    assert created["user_id"] == session_user
    assert "user-alien" not in {c.user_id for c in repo.contacts.values()}

    note = await ct.crm_add_note.ainvoke(
        {
            "body": "Follow-up amanhã",
            "contact_id": created["id"],
            "user_id": "user-alien",
        }
    )
    assert note["user_id"] == session_user
    assert note["source"] == NoteSource.AGENT.value
    saved = repo.notes[note["id"]]
    assert saved.user_id == session_user
    assert saved.source == NoteSource.AGENT


async def test_crm_move_deal_writes_note_with_source_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """unit-2 (REQ-002/REQ-004 deal-pipeline-state-machine): crm_move_deal
    (tool do agente) grava crm_notes com source='agent'."""
    from src.application.use_cases.move_crm_deal import MoveCrmDeal

    session_user = "user-a"
    _stub_resolved_user_id(monkeypatch, session_user)
    repo = _FakeCrmRepository()
    deal = Deal(id="deal-1", user_id=session_user, title="Deal", stage=DealStage.QUALIFIED)
    repo.deals[deal.id] = deal
    monkeypatch.setattr(
        ct, "build_move_crm_deal", lambda: MoveCrmDeal(repository=repo)
    )

    result = await ct.crm_move_deal.ainvoke({"deal_id": deal.id, "stage": "proposal"})

    assert result["stage"] == "proposal"
    assert len(repo.notes) == 1
    saved_note = next(iter(repo.notes.values()))
    assert saved_note.deal_id == deal.id
    assert saved_note.body == "qualified → proposal"
    assert saved_note.source == NoteSource.AGENT
