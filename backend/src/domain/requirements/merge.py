"""Domain service de consolidação — ordena e agrega seções num documento.

Reproduz a regra hoje embutida em `merge_generated_files`: ordenar as seções por
nome e concatená-las na ordem. Puro: sem framework, sem I/O.
"""
from __future__ import annotations

from collections.abc import Iterable

from src.domain.requirements.document_section import DocumentSection
from src.domain.requirements.requirement_document import RequirementDocument


def consolidate(sections: Iterable[DocumentSection]) -> RequirementDocument:
    """Ordena as seções por nome e retorna o `RequirementDocument` consolidado."""
    ordered = tuple(sorted(sections, key=lambda section: section.name))
    return RequirementDocument(sections=ordered)
