"""Templates filesystem + Jinja2 (html-document-tools-task-template-1)."""
from __future__ import annotations

from pathlib import Path

import pytest

from src.application.documents.resolve_html_document_input import (
    resolve_html_document_input,
)
from src.domain.shared.errors import DomainError
from src.infrastructure.documents.html_template_repository import (
    FilesystemHtmlTemplateRepository,
)
from src.models.html_document_input import HtmlDocumentInput

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_TEMPLATES_ROOT = _BACKEND_ROOT / "templates" / "documents"


def test_proposal_template_assets_exist() -> None:
    """AC: assets em backend/templates/documents/proposal/."""
    proposal = _TEMPLATES_ROOT / "proposal"
    assert (proposal / "template.html").is_file()
    assert (proposal / "styles.css").is_file()


def test_proposal_template_renders_with_minimal_data() -> None:
    """Unit-1: template proposal renderiza seções + CSS."""
    repo = FilesystemHtmlTemplateRepository(root=_TEMPLATES_ROOT)
    html, css = repo.render(
        "proposal",
        {
            "client_name": "Acme Ltda",
            "project_title": "Portal Interno",
            "summary": "Entrega do MVP em 8 semanas.",
            "investment": "R$ 48.000",
        },
    )
    assert "Acme Ltda" in html
    assert "Portal Interno" in html
    assert "proposta" in html.lower() or "proposal" in html.lower()
    assert css is not None
    assert "font-family" in css or "{" in css

    resolved = resolve_html_document_input(
        HtmlDocumentInput(
            template="proposal",
            data={"client_name": "Acme Ltda", "project_title": "Portal Interno"},
            title="Proposta Acme",
        ),
        render_template=repo.render,
    )
    assert resolved.template == "proposal"
    assert "Acme Ltda" in resolved.html
    assert resolved.css is not None


def test_unknown_template_fails_clean(tmp_path: Path) -> None:
    """Unit-2: template inexistente falha sem artefato."""
    repo = FilesystemHtmlTemplateRepository(root=_TEMPLATES_ROOT)
    with pytest.raises(DomainError, match="[Tt]emplate"):
        repo.render("does-not-exist", {})

    with pytest.raises(DomainError, match="[Tt]emplate"):
        resolve_html_document_input(
            HtmlDocumentInput(template="does-not-exist", data={}),
            render_template=repo.render,
        )
    assert list(tmp_path.iterdir()) == []
