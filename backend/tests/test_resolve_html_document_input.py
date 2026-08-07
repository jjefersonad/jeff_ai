"""Resolver de input HTML unificado (html-document-tools-task-input-1)."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.application.documents.resolve_html_document_input import (
    ResolvedHtmlDocument,
    parse_tool_payload,
    resolve_html_document_input,
)
from src.domain.shared.errors import DomainError
from src.models.html_document_input import HtmlBlockInput, HtmlDocumentInput


def test_blocks_resolve_to_semantic_html() -> None:
    """Unit-1: title + blocks → h1/h2, p, ul/ol, table."""
    payload = HtmlDocumentInput(
        title="Relatório",
        blocks=[
            HtmlBlockInput(type="heading", text="Resumo", level=1),
            HtmlBlockInput(type="heading", text="Detalhe", level=2),
            HtmlBlockInput(type="paragraph", text="Corpo do texto."),
            HtmlBlockInput(
                type="list",
                items=["A", "B"],
                ordered=False,
            ),
            HtmlBlockInput(
                type="list",
                items=["Um", "Dois"],
                ordered=True,
            ),
            HtmlBlockInput(
                type="table",
                rows=[["Mês", "Valor"], ["Jan", "10"]],
                header=True,
            ),
        ],
    )
    resolved = resolve_html_document_input(payload)
    assert isinstance(resolved, ResolvedHtmlDocument)
    html = resolved.html
    assert "<h1>Resumo</h1>" in html
    assert "<h2>Detalhe</h2>" in html
    assert "<p>Corpo do texto.</p>" in html
    assert "<ul>" in html and "<li>A</li>" in html
    assert "<ol>" in html and "<li>Um</li>" in html
    assert "<table>" in html and "<th>Mês</th>" in html and "<td>Jan</td>" in html
    assert resolved.title == "Relatório"
    assert resolved.css is None
    assert resolved.template is None


def test_html_and_template_together_rejected() -> None:
    """Unit-2: html + template no mesmo payload falha sem resolver HTML."""
    with pytest.raises(ValidationError, match="html e template"):
        HtmlDocumentInput(
            html="<p>x</p>",
            template="proposal",
            data={"client": "Acme"},
        )

    # Objeto construído à mão (bypass parcial) ainda é rejeitado no resolve.
    raw = HtmlDocumentInput.model_construct(
        html="<p>x</p>",
        template="proposal",
        data={"client": "Acme"},
        blocks=[],
    )
    with pytest.raises(DomainError, match="html e template"):
        resolve_html_document_input(raw)


def test_parse_tool_payload_rejects_plain_string() -> None:
    """Unit-3: string simples não-JSON → DomainError (tools → {error})."""
    with pytest.raises(DomainError, match="string simples"):
        parse_tool_payload("Só um título")


@pytest.mark.asyncio
async def test_create_pdf_document_rejects_plain_string_via_resolver() -> None:
    """Unit-3: create_pdf_document continua rejeitando string simples."""
    import src.tools.create_pdf_document_tool as pdf_tool

    out = await pdf_tool.create_pdf_document.coroutine("Só um título")
    assert "error" in out
    assert "path" not in out
    assert "url" not in out
