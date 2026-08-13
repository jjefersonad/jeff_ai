"""Testes de `is_stale(deal)` (sales-pipeline-via-agent-task-backend-deal-2).

Unit-1 (REQ-006): deal em `proposal` sem nota há 4 dias -> estagnado.
Unit-2 (REQ-006): deal em `won` nunca é estagnado, independente da idade da nota.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from src.domain.crm import Deal, DealStage
from src.domain.crm.stagnation import is_stale


def _deal(stage: DealStage, **overrides: object) -> Deal:
    defaults: dict[str, object] = dict(
        id="deal-1",
        user_id="user-a",
        title="Deal",
        stage=stage,
        created_at=datetime.now(UTC) - timedelta(days=30),
        updated_at=datetime.now(UTC) - timedelta(days=30),
    )
    defaults.update(overrides)
    return Deal(**defaults)  # type: ignore[arg-type]


def test_proposal_stale_after_4_days_without_note() -> None:
    """unit-1 (REQ-006): proposal (limiar 3d) sem nota há 4d -> True."""
    now = datetime.now(UTC)
    deal = _deal(DealStage.PROPOSAL)
    last_note_at = now - timedelta(days=4)
    assert is_stale(deal, last_note_at=last_note_at, now=now) is True


def test_won_never_stale_regardless_of_note_age() -> None:
    """unit-2 (REQ-006): won nunca estagna, mesmo sem nota há muito tempo."""
    now = datetime.now(UTC)
    deal = _deal(DealStage.WON)
    very_old_note = now - timedelta(days=3650)
    assert is_stale(deal, last_note_at=very_old_note, now=now) is False
    assert is_stale(deal, last_note_at=None, now=now) is False


def test_lost_never_stale() -> None:
    """won/lost nunca são estagnados (REQ-006)."""
    now = datetime.now(UTC)
    deal = _deal(DealStage.LOST)
    assert is_stale(deal, last_note_at=None, now=now) is False


def test_qualified_threshold_is_7_days() -> None:
    """qualified: limiar 7 dias — 6d não estagna, 8d estagna."""
    now = datetime.now(UTC)
    deal = _deal(DealStage.QUALIFIED)
    assert is_stale(deal, last_note_at=now - timedelta(days=6), now=now) is False
    assert is_stale(deal, last_note_at=now - timedelta(days=8), now=now) is True


def test_negotiation_threshold_is_2_days() -> None:
    """negotiation: limiar 2 dias."""
    now = datetime.now(UTC)
    deal = _deal(DealStage.NEGOTIATION)
    assert is_stale(deal, last_note_at=now - timedelta(days=1), now=now) is False
    assert is_stale(deal, last_note_at=now - timedelta(days=3), now=now) is True


def test_no_notes_ever_falls_back_to_deal_created_at() -> None:
    """Sem nenhuma nota -> usa `deal.created_at` como última atividade."""
    now = datetime.now(UTC)
    deal = _deal(DealStage.PROPOSAL, created_at=now - timedelta(days=5))
    assert is_stale(deal, last_note_at=None, now=now) is True

    fresh_deal = _deal(DealStage.PROPOSAL, created_at=now - timedelta(hours=1))
    assert is_stale(fresh_deal, last_note_at=None, now=now) is False
