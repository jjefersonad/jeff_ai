"""Domínio SDD — feature, numeração e estado do pipeline (puro)."""
from src.domain.sdd.feature import Feature
from src.domain.sdd.feature_number import FeatureNumber
from src.domain.sdd.phase import PHASE_ORDER, PhaseStatus, SddPhase
from src.domain.sdd.pipeline import is_pipeline_complete, next_phase
from src.domain.sdd.validation import (
    ArtifactValidation,
    SectionCheck,
    known_artifact_types,
    validate_sections,
)

__all__ = [
    "PHASE_ORDER",
    "ArtifactValidation",
    "Feature",
    "FeatureNumber",
    "PhaseStatus",
    "SddPhase",
    "SectionCheck",
    "is_pipeline_complete",
    "known_artifact_types",
    "next_phase",
    "validate_sections",
]
