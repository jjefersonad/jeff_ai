"""Testes da skill pdf (add-pdf-creation-tool-task-skill-1)."""
from __future__ import annotations

from pathlib import Path

SKILL_PATH = (
    Path(__file__).resolve().parents[1] / "skills" / "pdf" / "SKILL.md"
)


def test_pdf_skill_documents_contract_and_limits() -> None:
    """Unit: skill pdf documenta contrato."""
    content = SKILL_PATH.read_text(encoding="utf-8")
    assert "create_pdf_document" in content
    assert "url" in content
    assert "fpdf2" in content
    # Edição de PDF existente fora de escopo.
    lowered = content.lower()
    assert "existente" in lowered
    assert "fora do escopo" in lowered or "não é suportada" in lowered
    assert "editar" in lowered or "edição" in lowered
