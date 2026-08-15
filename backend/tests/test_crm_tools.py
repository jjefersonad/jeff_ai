"""Testes de `src/tools/crm_tools.py` (add-simple-crm-module-task-tools-1).

Unit-1 (REQ-003): sem identidade resolvível → erro e não consulta o repositório.
Unit-2 (REQ-003): `user_id` no payload do modelo é ignorado; usa só a sessão.
REQ-006 (saas-empresario-br-task-crm-api-2): `crm_upsert_contact` aceita
`whatsapp_opt_in` e não dispara WhatsApp; update cross-user falha.
"""
from __future__ import annotations

import inspect

import pytest
from crm_repository_fakes import CrmRepositoryPortExtensions

import src.tools.crm_tools as ct
from src.application.ports.crm_repository import CrmRepositoryPort
from src.application.use_cases.create_crm_contact import CreateCrmContact
from src.application.use_cases.create_crm_note import CreateCrmNote
from src.application.use_cases.list_crm_contacts import ListCrmContacts
from src.application.use_cases.update_crm_contact import UpdateCrmContact
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


def _wire_upsert(monkeypatch: pytest.MonkeyPatch, repo: _FakeCrmRepository) -> None:
    monkeypatch.setattr(
        ct, "build_create_crm_contact", lambda: CreateCrmContact(repository=repo)
    )
    monkeypatch.setattr(
        ct, "build_update_crm_contact", lambda: UpdateCrmContact(repository=repo)
    )


async def test_crm_upsert_contact_whatsapp_opt_in_true_persists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REQ-006 unit-1: opt-in true na sessão persiste true no create e no update."""
    session_user = "user-a"
    _stub_resolved_user_id(monkeypatch, session_user)
    repo = _FakeCrmRepository()
    _wire_upsert(monkeypatch, repo)

    created = await ct.crm_upsert_contact.ainvoke(
        {
            "name": "Ana",
            "email": "ana@example.com",
            "whatsapp_opt_in": True,
        }
    )
    assert created["whatsapp_opt_in"] is True
    assert repo.contacts[created["id"]].whatsapp_opt_in is True

    created_false = await ct.crm_upsert_contact.ainvoke(
        {
            "name": "Bruno",
            "email": "bruno@example.com",
        }
    )
    assert created_false["whatsapp_opt_in"] is False

    updated = await ct.crm_upsert_contact.ainvoke(
        {
            "contact_id": created_false["id"],
            "name": "Bruno",
            "email": "bruno@example.com",
            "whatsapp_opt_in": True,
        }
    )
    assert updated["whatsapp_opt_in"] is True
    assert repo.contacts[created_false["id"]].whatsapp_opt_in is True


async def test_crm_upsert_contact_whatsapp_opt_in_none_defaults_and_preserves(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REQ-006 unit-1: None no create → false; None no update → preserva."""
    session_user = "user-a"
    _stub_resolved_user_id(monkeypatch, session_user)
    repo = _FakeCrmRepository()
    _wire_upsert(monkeypatch, repo)

    created = await ct.crm_upsert_contact.ainvoke(
        {
            "name": "Ana",
            "email": "ana@example.com",
        }
    )
    assert created["whatsapp_opt_in"] is False
    assert repo.contacts[created["id"]].whatsapp_opt_in is False

    opted = await ct.crm_upsert_contact.ainvoke(
        {
            "contact_id": created["id"],
            "name": "Ana",
            "email": "ana@example.com",
            "whatsapp_opt_in": True,
        }
    )
    assert opted["whatsapp_opt_in"] is True

    preserved = await ct.crm_upsert_contact.ainvoke(
        {
            "contact_id": created["id"],
            "name": "Ana Silva",
            "email": "ana@example.com",
        }
    )
    assert preserved["name"] == "Ana Silva"
    assert preserved["whatsapp_opt_in"] is True
    assert repo.contacts[created["id"]].whatsapp_opt_in is True


async def test_crm_upsert_contact_whatsapp_opt_in_does_not_send_whatsapp() -> None:
    """REQ-006 unit-1: a tool não dispara WhatsApp com base no opt-in."""
    source = inspect.getsource(ct.crm_upsert_contact.coroutine)
    lowered = source.lower()
    assert "evolution" not in lowered
    assert "send_message" not in source
    assert "send_whatsapp" not in lowered


async def test_crm_upsert_contact_whatsapp_opt_in_foreign_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REQ-006 unit-2: update de contato de outro user falha; opt-in do dono intacto."""
    repo = _FakeCrmRepository()
    _wire_upsert(monkeypatch, repo)

    _stub_resolved_user_id(monkeypatch, "user-a")
    created = await ct.crm_upsert_contact.ainvoke(
        {
            "name": "Ana",
            "email": "ana@example.com",
        }
    )
    assert created["whatsapp_opt_in"] is False
    contact_id = created["id"]

    _stub_resolved_user_id(monkeypatch, "user-b")
    result = await ct.crm_upsert_contact.ainvoke(
        {
            "contact_id": contact_id,
            "name": "Ana",
            "email": "ana@example.com",
            "whatsapp_opt_in": True,
        }
    )
    assert isinstance(result, dict)
    assert "error" in result
    assert result["error"] == "Contact not found"
    assert "whatsapp_opt_in" not in result
    owner = repo.contacts[contact_id]
    assert owner.user_id == "user-a"
    assert owner.whatsapp_opt_in is False
