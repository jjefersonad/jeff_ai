"""Testes do domínio de requirements (domain-model REQ-003/REQ-004).

Puro: sem framework, sem I/O — cobre invariantes, ordenação/merge e renderização.
"""
import pytest

from src.domain.requirements import DocumentSection, RequirementDocument, consolidate
from src.domain.shared.errors import DomainError


@pytest.mark.parametrize("name", ["", "   "])
def test_document_section_requires_name(name):
    with pytest.raises(DomainError):
        DocumentSection(name, "conteúdo")


def test_document_section_rejects_non_string_content():
    with pytest.raises(DomainError):
        DocumentSection("a.md", 123)


def test_consolidate_orders_sections_by_name():
    """domain-model REQ-004: a regra de merge ordena por nome."""
    sections = [
        DocumentSection("02_body.md", "B"),
        DocumentSection("01_intro.md", "A"),
        DocumentSection("03_end.md", "C"),
    ]
    doc = consolidate(sections)
    assert [s.name for s in doc.sections] == ["01_intro.md", "02_body.md", "03_end.md"]


def test_consolidate_empty_is_empty_document():
    doc = consolidate([])
    assert doc.is_empty()
    assert doc.render() == ""


def test_render_uses_start_end_markers_in_order():
    """domain-model REQ-004: renderização com marcadores INÍCIO/FIM por seção."""
    doc = consolidate(
        [DocumentSection("b.md", "B"), DocumentSection("a.md", "A")]
    )
    expected = (
        "\n// --- INÍCIO DO ARQUIVO: a.md ---\nA\n// --- FIM DO ARQUIVO: a.md ---\n\n"
        "\n// --- INÍCIO DO ARQUIVO: b.md ---\nB\n// --- FIM DO ARQUIVO: b.md ---\n\n"
    )
    assert doc.render() == expected


def test_requirement_document_rejects_non_section_items():
    with pytest.raises(DomainError):
        RequirementDocument(sections=("não é uma seção",))
