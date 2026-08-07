"""Skills de documento — pipeline HTML + preview-first (html-document-tools-task-skills-1)."""
from __future__ import annotations

from pathlib import Path

SKILLS = Path(__file__).resolve().parents[1] / "skills"


def _read(skill: str) -> str:
    path = SKILLS / skill / "SKILL.md"
    assert path.is_file(), f"missing {path}"
    return path.read_text(encoding="utf-8")


def test_pdf_skill_mentions_html_template_not_fpdf2_api() -> None:
    """Unit-1: pdf skill → HTML/template + create_pdf_document; não API fpdf2."""
    content = _read("pdf")
    lowered = content.lower()
    assert "create_pdf_document" in content
    assert "html" in lowered or "template" in lowered
    assert "weasyprint" in lowered or "pipeline" in lowered
    # Não apresentar fpdf2 como API canônica do agente.
    assert "create_pdf_document` (fpdf2)" not in content
    assert "biblioteca `fpdf2`" not in content


def test_proposal_skill_documents_template_and_pdf() -> None:
    """Unit-2: skill proposal cita template proposal + create_pdf_document / kind pdf."""
    content = _read("proposal")
    lowered = content.lower()
    assert "proposal" in lowered  # template name
    assert "create_pdf_document" in content
    assert "pdf" in lowered


def test_proposal_or_pdf_skill_preview_first() -> None:
    """Unit-3: proposal/pdf citam preview_html_document e revisão antes do final."""
    proposal = _read("proposal")
    pdf = _read("pdf")
    combined = proposal + "\n" + pdf
    assert "preview_html_document" in combined
    lowered = combined.lower()
    assert "revis" in lowered or "preview" in lowered or "web" in lowered
    # Fluxo principal de proposta não é só create_pdf direto.
    assert "from_preview" in combined or "preview_html_document" in proposal
