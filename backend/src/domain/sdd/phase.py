"""Fases do pipeline SDD e seus estados."""
from __future__ import annotations

from enum import Enum


class SddPhase(str, Enum):
    """As 7 fases do pipeline Spec-Driven Development."""

    CONSTITUTION = "constitution"
    SPECIFY = "specify"
    CLARIFY = "clarify"
    PLAN = "plan"
    ANALYZE = "analyze"
    TASKS = "tasks"
    IMPLEMENT = "implement"


class PhaseStatus(str, Enum):
    """Estado de uma fase quanto ao seu artefato."""

    COMPLETE = "complete"
    PLACEHOLDER = "placeholder"
    MISSING = "missing"


# Ordem canônica do pipeline de 7 fases.
PHASE_ORDER: tuple[SddPhase, ...] = (
    SddPhase.CONSTITUTION,
    SddPhase.SPECIFY,
    SddPhase.CLARIFY,
    SddPhase.PLAN,
    SddPhase.ANALYZE,
    SddPhase.TASKS,
    SddPhase.IMPLEMENT,
)
