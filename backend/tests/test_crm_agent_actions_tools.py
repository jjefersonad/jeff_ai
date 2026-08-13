"""Testes das tools do grupo `backend-agent-actions` (sales-pipeline-via-agent).

`request_followup` (task backend-agent-actions-1):
Unit-1 (REQ-002): sem `draft`, chama `next_best_action.suggest()` sobre as
notas reais do deal e usa o `editable_text` devolvido.
Unit-2 (REQ-002): com `draft`, usa esse texto verbatim, sem consultar notas.

`add_deal_note` (task backend-agent-actions-2):
Unit-1 (REQ-003): cria `crm_notes(deal_id, body=text, source='agent')`.

`crm_move_deal` (task backend-agent-actions-3, verificação):
Unit-1 (REQ-001 agent-driven-deal-actions): movimento via chat passa pelo
mesmo use case (`MoveCrmDeal`) do endpoint REST e grava nota `source='agent'`.
"""
from __future__ import annotations

import pytest
from crm_repository_fakes import CrmRepositoryPortExtensions

import src.tools.crm_tools as ct
from src.application.ports.crm_repository import CrmRepositoryPort
from src.application.use_cases.get_crm_deal import GetCrmDeal
from src.application.use_cases.list_crm_notes import ListCrmNotes
from src.domain.crm import Deal, DealStage, Note, NoteSource


class _FakeCrmRepository(CrmRepositoryPortExtensions, CrmRepositoryPort):
    def __init__(self) -> None:
        self.deals: dict[str, Deal] = {}
        self.notes_for_deal: dict[str, list[Note]] = {}
        self.list_notes_for_deal_calls: list[str] = []
        self.notes: dict[str, Note] = {}

    async def create_company(self, company):  # pragma: no cover - unused
        raise NotImplementedError

    async def get_company(self, user_id, company_id):
        return None

    async def list_companies(self, user_id, *, query=None, include_archived=False):
        return []

    async def update_company(self, company):
        return None

    async def archive_company(self, user_id, company_id):
        return None

    async def create_contact(self, contact):  # pragma: no cover - unused
        raise NotImplementedError

    async def get_contact(self, user_id, contact_id):
        return None

    async def list_contacts(self, user_id, *, query=None, company_id=None, include_archived=False):
        return []

    async def update_contact(self, contact):
        return None

    async def archive_contact(self, user_id, contact_id):
        return None

    async def create_deal(self, deal):  # pragma: no cover - unused
        raise NotImplementedError

    async def get_deal(self, user_id: str, deal_id: str) -> Deal | None:
        deal = self.deals.get(deal_id)
        if deal is None or deal.user_id != user_id:
            return None
        return deal

    async def list_deals(self, user_id, *, stage=None, include_archived=False):
        return []

    async def update_deal(self, deal):
        return None

    async def archive_deal(self, user_id, deal_id):
        return None

    async def move_deal(self, user_id, deal_id, stage):
        deal = await self.get_deal(user_id, deal_id)
        if deal is None:
            return None
        deal.stage = stage
        self.deals[deal.id] = deal
        return deal

    async def create_note(self, note: Note) -> Note:
        self.notes[note.id] = note
        return note

    async def list_notes_for_contact(self, user_id, contact_id, *, include_archived=False):
        return []

    async def list_notes_for_company(self, user_id, company_id, *, include_archived=False):
        return []

    async def list_notes_for_deal(
        self, user_id: str, deal_id: str, *, include_archived: bool = False
    ) -> list[Note]:
        self.list_notes_for_deal_calls.append(deal_id)
        return self.notes_for_deal.get(deal_id, [])


def _stub_resolved_user_id(monkeypatch: pytest.MonkeyPatch, user_id: str | None) -> None:
    async def _fake_resolve_user_id() -> str | None:
        return user_id

    monkeypatch.setattr(ct, "resolve_user_id", _fake_resolve_user_id)


def _seed_deal(repo: _FakeCrmRepository, *, deal_id: str = "deal-1") -> Deal:
    deal = Deal(id=deal_id, user_id="user-a", title="Acme", stage=DealStage.PROPOSAL)
    repo.deals[deal.id] = deal
    return deal


async def test_request_followup_without_draft_generates_via_suggest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """unit-1 (REQ-002): sem `draft`, gera o rascunho via `next_best_action.suggest()`
    citando a proposta enviada há 3 dias, presente nas notas reais do deal."""
    _stub_resolved_user_id(monkeypatch, "user-a")
    repo = _FakeCrmRepository()
    deal = _seed_deal(repo)
    from datetime import UTC, datetime, timedelta

    now = datetime.now(UTC)
    repo.notes_for_deal[deal.id] = [
        Note(
            id="note-1",
            user_id="user-a",
            body="Proposta enviada por email",
            source=NoteSource.AGENT,
            deal_id=deal.id,
            created_at=now - timedelta(days=3),
        )
    ]
    monkeypatch.setattr(ct, "build_get_crm_deal", lambda: GetCrmDeal(repository=repo))
    monkeypatch.setattr(ct, "build_list_crm_notes", lambda: ListCrmNotes(repository=repo))

    result = await ct.request_followup.ainvoke({"deal_id": deal.id})

    assert repo.list_notes_for_deal_calls == [deal.id]
    assert "3 dias" in result["draft_text"]
    assert result["deal_id"] == deal.id


async def test_request_followup_with_draft_uses_it_verbatim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """unit-2 (REQ-002): com `draft`, usa o texto fornecido verbatim, sem
    consultar as notas do deal."""
    _stub_resolved_user_id(monkeypatch, "user-a")
    repo = _FakeCrmRepository()
    deal = _seed_deal(repo)
    monkeypatch.setattr(ct, "build_get_crm_deal", lambda: GetCrmDeal(repository=repo))
    monkeypatch.setattr(ct, "build_list_crm_notes", lambda: ListCrmNotes(repository=repo))

    result = await ct.request_followup.ainvoke({"deal_id": deal.id, "draft": "Oi João"})

    assert result["draft_text"] == "Oi João"
    assert repo.list_notes_for_deal_calls == []


async def test_add_deal_note_creates_note_with_source_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """unit-1 (REQ-003): `add_deal_note(deal_id, text)` cria diretamente
    `crm_notes(deal_id, body=text, source='agent')`."""
    from src.application.use_cases.create_crm_note import CreateCrmNote

    _stub_resolved_user_id(monkeypatch, "user-a")
    repo = _FakeCrmRepository()
    deal = _seed_deal(repo)
    monkeypatch.setattr(ct, "build_create_crm_note", lambda: CreateCrmNote(repository=repo))

    result = await ct.add_deal_note.ainvoke(
        {"deal_id": deal.id, "text": "cliente pediu prazo até sexta"}
    )

    assert result["deal_id"] == deal.id
    assert result["body"] == "cliente pediu prazo até sexta"
    assert result["source"] == NoteSource.AGENT.value
    saved = repo.notes[result["id"]]
    assert saved.deal_id == deal.id
    assert saved.body == "cliente pediu prazo até sexta"
    assert saved.source == NoteSource.AGENT
    assert saved.user_id == "user-a"


async def test_crm_move_deal_from_chat_uses_same_use_case_as_rest_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """unit-1 (REQ-001 agent-driven-deal-actions): `crm_move_deal` chamado
    pelo chat passa por `MoveCrmDeal` — o MESMO use case que
    `POST /api/crm/deals/{id}/move` usa no kanban (`crm_router.move_deal_endpoint`)
    — e grava a nota de transição com `source='agent'` (REQ-004: nenhum
    caminho escreve em `crm_deals` fora desse use case compartilhado)."""
    from src.application.use_cases.move_crm_deal import MoveCrmDeal

    _stub_resolved_user_id(monkeypatch, "user-a")
    repo = _FakeCrmRepository()
    deal = _seed_deal(repo)
    deal.stage = DealStage.QUALIFIED
    monkeypatch.setattr(ct, "build_move_crm_deal", lambda: MoveCrmDeal(repository=repo))

    result = await ct.crm_move_deal.ainvoke({"deal_id": deal.id, "stage": "proposal"})

    assert result["stage"] == "proposal"
    assert len(repo.notes) == 1
    saved_note = next(iter(repo.notes.values()))
    assert saved_note.deal_id == deal.id
    assert saved_note.source == NoteSource.AGENT
