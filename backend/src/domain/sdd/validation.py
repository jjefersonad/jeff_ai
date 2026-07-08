"""Regra de validação estrutural de artefatos SDD (seções obrigatórias + veredito)."""
from __future__ import annotations

from dataclasses import dataclass

from src.domain.shared.errors import DomainError

# Regra de negócio: quais seções cada tipo de artefato SDD deve conter.
REQUIRED_SECTIONS: dict[str, tuple[str, ...]] = {
    "constitution": (
        "Core Principles",
        "Technology Constraints",
        "Development Workflow",
        "Quality Gates",
    ),
    "spec": (
        "Overview",
        "User Scenarios",
        "Functional Requirements",
        "Non-Functional Requirements",
        "Key Entities",
    ),
    "plan": (
        "Architecture Overview",
        "Technology Stack",
        "Component Design",
        "API Design",
        "Implementation Phases",
    ),
    "tasks": ("Dependency Graph", "Phase 1:", "Checkpoint"),
    "data-model": ("Entity Relationship Overview", "Entities", "Validation Rules"),
}


@dataclass(frozen=True)
class SectionCheck:
    """Resultado da checagem de uma seção obrigatória."""

    section: str
    passed: bool


@dataclass(frozen=True)
class ArtifactValidation:
    """Veredito da validação de um artefato: PASS/FAIL/WARN + checagens por seção."""

    verdict: str
    checks: tuple[SectionCheck, ...]

    @property
    def pass_count(self) -> int:
        """Número de seções presentes."""
        return sum(1 for c in self.checks if c.passed)

    @property
    def fail_count(self) -> int:
        """Número de seções ausentes."""
        return sum(1 for c in self.checks if not c.passed)


def known_artifact_types() -> tuple[str, ...]:
    """Tipos de artefato SDD reconhecidos (na ordem canônica)."""
    return tuple(REQUIRED_SECTIONS.keys())


def validate_sections(artifact_type: str, content: str) -> ArtifactValidation:
    """Verifica as seções obrigatórias no `content` e calcula o veredito.

    PASS se todas presentes; FAIL se nenhuma; WARN caso parcial.
    """
    if artifact_type not in REQUIRED_SECTIONS:
        raise DomainError(f"Tipo de artefato inválido: {artifact_type!r}.")

    checks = tuple(
        SectionCheck(section=section, passed=section.lower() in content.lower())
        for section in REQUIRED_SECTIONS[artifact_type]
    )
    fails = sum(1 for c in checks if not c.passed)
    passes = len(checks) - fails
    if fails == 0:
        verdict = "PASS"
    elif passes == 0:
        verdict = "FAIL"
    else:
        verdict = "WARN"
    return ArtifactValidation(verdict=verdict, checks=checks)
