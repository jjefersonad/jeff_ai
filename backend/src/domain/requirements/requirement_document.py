"""Entidade `RequirementDocument` — agregação ordenada de seções + renderização."""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from src.domain.requirements.document_section import DocumentSection
from src.domain.shared.errors import DomainError

# Marcadores de início/fim por seção (idênticos ao merge_generated_files legado).
_SECTION_START = "\n// --- INÍCIO DO ARQUIVO: {name} ---\n"
_SECTION_END = "\n// --- FIM DO ARQUIVO: {name} ---\n\n"


@dataclass(frozen=True)
class RequirementDocument:
    """Documento de requisitos consolidado: uma sequência ordenada de `DocumentSection`."""

    sections: tuple[DocumentSection, ...] = ()

    def __post_init__(self) -> None:
        """Garante que `sections` seja uma tupla de `DocumentSection`."""
        if not all(isinstance(s, DocumentSection) for s in self.sections):
            raise DomainError(
                "RequirementDocument.sections deve conter apenas DocumentSection."
            )
        object.__setattr__(self, "sections", tuple(self.sections))

    def is_empty(self) -> bool:
        """Indica se o documento não tem seções."""
        return len(self.sections) == 0

    def render(self) -> str:
        """Renderiza o documento consolidado com os marcadores de início/fim por seção."""
        parts: list[str] = []
        for section in self.sections:
            parts.append(_SECTION_START.format(name=section.name))
            parts.append(section.content)
            parts.append(_SECTION_END.format(name=section.name))
        return "".join(parts)

    @classmethod
    def from_sections(cls, sections: Sequence[DocumentSection]) -> RequirementDocument:
        """Cria o documento a partir de uma sequência de seções (na ordem dada)."""
        return cls(sections=tuple(sections))
