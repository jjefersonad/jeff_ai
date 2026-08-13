"""Detecção de estagnação de deals (REQ-006 deal-pipeline-state-machine).

PURO: zero import de framework/repositório — `is_stale` recebe o timestamp
da nota mais recente já resolvido pelo chamador (`next_best_action`, tasks
`backend-nba-*`), não consulta `crm_notes` sozinho.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from src.domain.crm.models import Deal, DealStage

# `None` = nunca estagna (won/lost).
_STALE_THRESHOLD_DAYS: dict[DealStage, int | None] = {
    DealStage.LEAD: 7,
    DealStage.QUALIFIED: 7,
    DealStage.PROPOSAL: 3,
    DealStage.NEGOTIATION: 2,
    DealStage.WON: None,
    DealStage.LOST: None,
}


def is_stale(
    deal: Deal,
    *,
    last_note_at: datetime | None,
    now: datetime | None = None,
) -> bool:
    """Indica se o deal não tem sinal de atividade há mais que o limiar do estágio.

    "Sinal de atividade" é a `crm_notes` mais recente (`last_note_at`); se o
    deal nunca teve nenhuma nota, usa `deal.created_at` como referência.
    `won`/`lost` nunca estagnam.
    """
    threshold_days = _STALE_THRESHOLD_DAYS[deal.stage]
    if threshold_days is None:
        return False
    reference = now if now is not None else datetime.now(UTC)
    last_activity = last_note_at if last_note_at is not None else deal.created_at
    return reference - last_activity > timedelta(days=threshold_days)
