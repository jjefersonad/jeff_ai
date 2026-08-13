"""Testes de `next_best_action.suggest(notes)` (sales-pipeline-via-agent-task-backend-nba-1)
e `next_best_action.suggest_all(deals)` (sales-pipeline-via-agent-task-backend-nba-2).

Unit-1 (REQ-001): nota de 3 dias mencionando proposta -> rascunho cita "há 3 dias".
Unit-2 (REQ-001): sem nota mencionando proposta -> rascunho nunca afirma envio.
Unit-1 (REQ-004, nba-2): 25 deals estagnados -> só os 10 mais antigos voltam.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from src.domain.crm import (
    Deal,
    DealStage,
    Note,
    NoteSource,
    next_best_action,
)


def _note(body: str, *, created_at: datetime) -> Note:
    return Note(
        id=str(uuid.uuid4()),
        user_id="user-a",
        body=body,
        source=NoteSource.SYSTEM,
        deal_id="deal-1",
        created_at=created_at,
    )


def _deal(deal_id: str, *, created_at: datetime) -> Deal:
    return Deal(
        id=deal_id,
        user_id="user-a",
        title=f"Deal {deal_id}",
        stage=DealStage.QUALIFIED,
        created_at=created_at,
        updated_at=created_at,
    )


def test_draft_references_real_proposal_note_timing() -> None:
    """unit-1 (REQ-001): nota de proposta há 3 dias -> rascunho cita "há 3 dias"."""
    now = datetime.now(UTC)
    notes = [_note("Email recebido: Proposta v2", created_at=now - timedelta(days=3))]

    result = next_best_action.suggest(notes, now=now)

    assert "há 3 dias" in result["editable_text"]
    assert "ontem" not in result["editable_text"]
    assert "semana passada" not in result["editable_text"]


def test_draft_never_invents_proposal_when_no_note_mentions_it() -> None:
    """unit-2 (REQ-001): sem nota de proposta -> rascunho não afirma envio."""
    now = datetime.now(UTC)
    notes = [
        _note("Ligação de qualificação realizada", created_at=now - timedelta(days=5))
    ]

    result = next_best_action.suggest(notes, now=now)

    assert "proposta enviada" not in result["editable_text"].lower()


def test_suggest_all_caps_at_10_oldest_of_25_stale_deals() -> None:
    """unit-1 (REQ-004): 25 deals estagnados (qualified, sem nota) -> só os 10 mais antigos."""
    now = datetime.now(UTC)
    # qualified estagna após 7 dias sem nota; todos aqui têm 10..34 dias (estagnados).
    deals = [
        _deal(f"deal-{i}", created_at=now - timedelta(days=10 + i)) for i in range(25)
    ]

    result = next_best_action.suggest_all(deals, now=now)

    assert len(result) == 10
    expected_ids = [f"deal-{i}" for i in range(24, 14, -1)]  # os 10 mais antigos primeiro
    assert [d.id for d in result] == expected_ids


# ---------------------------------------------------------------------------
# Task backend-nba-3 (REQ-005): `suggest()` anexa `calendar_slot` opcional
# para deals em `proposal`/`negotiation` quando há slot livre em 3 dias;
# sem slot, mantém `kind='email_followup'` e omite `calendar_slot`.
# ---------------------------------------------------------------------------


def test_suggest_proposal_with_free_slot_includes_calendar_slot() -> None:
    """unit-1 (REQ-005, nba-3): deal em `proposal` com slot 30min livre em
    3 dias -> `suggest` retorna `kind='meeting_proposal'` e anexa
    `calendar_slot` com `start`/`end`/`calendar_link`."""
    now = datetime.now(UTC)
    notes = [
        _note("Proposta enviada por email", created_at=now - timedelta(days=3))
    ]
    free_slot = {
        "start": "2026-08-15T14:00:00Z",
        "end": "2026-08-15T14:30:00Z",
        "calendar_link": "https://cal.example.com/event/abc",
    }

    def _slot_finder(*, duration_minutes: int, within_days: int) -> dict | None:
        assert duration_minutes == 30
        assert within_days == 3
        return free_slot

    result = next_best_action.suggest(
        notes,
        now=now,
        deal_stage=DealStage.PROPOSAL,
        slot_finder=_slot_finder,
    )

    assert result["kind"] == "meeting_proposal"
    assert result["calendar_slot"] == free_slot
    assert result["calendar_slot"]["start"] == free_slot["start"]
    assert result["calendar_slot"]["end"] == free_slot["end"]
    assert result["calendar_slot"]["calendar_link"] == free_slot["calendar_link"]


def test_suggest_without_free_slot_falls_back_to_email_followup() -> None:
    """unit-2 (REQ-005, nba-3): deal sem slot livre em 3 dias -> `suggest`
    OMITE `calendar_slot` e mantém `kind='email_followup'`."""
    now = datetime.now(UTC)
    notes = [
        _note("Proposta enviada por email", created_at=now - timedelta(days=3))
    ]

    def _slot_finder(*, duration_minutes: int, within_days: int) -> dict | None:
        return None  # sem slot livre

    result = next_best_action.suggest(
        notes,
        now=now,
        deal_stage=DealStage.PROPOSAL,
        slot_finder=_slot_finder,
    )

    assert "calendar_slot" not in result
    assert result["kind"] == "email_followup"
    # texto continua citando a nota real de proposta
    assert "há 3 dias" in result["editable_text"]
