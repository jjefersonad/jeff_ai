"""Domain service do pipeline SDD — determina a próxima fase incompleta.

Reproduz a regra de `get_sdd_state`: percorre as fases na ordem canônica e
retorna a primeira fase RASTREADA cujo estado é `missing`/`placeholder`. Fases
não rastreadas (sem status informado) não bloqueiam o avanço. Puro: sem I/O.
"""
from __future__ import annotations

from collections.abc import Mapping

from src.domain.sdd.phase import PHASE_ORDER, PhaseStatus, SddPhase

_INCOMPLETE = (PhaseStatus.MISSING, PhaseStatus.PLACEHOLDER)


def next_phase(statuses: Mapping[SddPhase, PhaseStatus]) -> SddPhase | None:
    """Retorna a próxima fase incompleta na ordem canônica, ou None se completa."""
    for phase in PHASE_ORDER:
        if phase in statuses and statuses[phase] in _INCOMPLETE:
            return phase
    return None


def is_pipeline_complete(statuses: Mapping[SddPhase, PhaseStatus]) -> bool:
    """Indica se todas as fases rastreadas estão completas."""
    return next_phase(statuses) is None
