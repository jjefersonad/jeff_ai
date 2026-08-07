"""Resolve `HtmlDocumentInput` (ou payload de tool) em HTML final + metadados."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Union

from pydantic import ValidationError

from src.domain.documents.blocks_to_html import blocks_to_html
from src.domain.shared.errors import DomainError
from src.models.html_document_input import HtmlDocumentInput

TemplateRenderer = Callable[[str, dict[str, Any]], tuple[str, str | None]]


@dataclass(frozen=True)
class ResolvedHtmlDocument:
    """HTML pronto para o pipeline (ainda sem sanitizar — isso é do RenderHtmlDocument)."""

    html: str
    css: str | None = None
    title: str | None = None
    template: str | None = None


def resolve_html_document_input(
    payload: HtmlDocumentInput,
    *,
    render_template: TemplateRenderer | None = None,
) -> ResolvedHtmlDocument:
    """Escolhe o modo html | template | blocks e produz HTML.

    `html` + `template` juntos já são rejeitados pelo validator Pydantic;
    reforçamos aqui com DomainError para quem construir o objeto à mão.
    """
    has_html = bool(payload.html and payload.html.strip())
    has_template = bool(payload.template and payload.template.strip())
    has_blocks = bool(payload.blocks)

    if has_html and has_template:
        raise DomainError(
            "Não combine html e template no mesmo payload; use um ou outro."
        )

    if has_html:
        return ResolvedHtmlDocument(
            html=payload.html.strip(),  # type: ignore[union-attr]
            css=payload.css,
            title=payload.title,
        )

    if has_template:
        name = payload.template.strip()  # type: ignore[union-attr]
        if render_template is None:
            raise DomainError(
                f"Template {name!r} requer um renderizador (ainda não configurado)."
            )
        data = payload.data or {}
        html, css = render_template(name, data)
        return ResolvedHtmlDocument(
            html=html,
            css=css,
            title=payload.title,
            template=name,
        )

    if has_blocks or (payload.title and payload.title.strip()):
        if not has_blocks:
            raise DomainError("blocks é obrigatório e não pode ficar vazio.")
        html = blocks_to_html(title=payload.title, blocks=payload.blocks)
        return ResolvedHtmlDocument(html=html, title=payload.title)

    raise DomainError(
        "Entrada vazia: informe html, template+data ou title+blocks não vazios."
    )


def parse_tool_payload(payload: Union[str, HtmlDocumentInput, Any]) -> HtmlDocumentInput:
    """Normaliza payload de tool (string JSON / modelo) para `HtmlDocumentInput`.

    String simples não-JSON → DomainError (tools traduzem para `{error}`).
    """
    if isinstance(payload, HtmlDocumentInput):
        return payload
    if isinstance(payload, str):
        stripped = payload.strip()
        if stripped.startswith("{"):
            try:
                parsed = json.loads(stripped)
                return HtmlDocumentInput.model_validate(parsed)
            except (json.JSONDecodeError, ValidationError) as exc:
                raise DomainError(f"payload JSON inválido: {exc}") from exc
        raise DomainError(
            "Entrada string simples requer conteúdo estruturado "
            "(html, template ou blocks); use HtmlDocumentInput ou JSON."
        )
    # Aceita modelos Pydantic parecidos (ex.: PdfDocumentInput) via dump.
    if hasattr(payload, "model_dump"):
        try:
            return HtmlDocumentInput.model_validate(payload.model_dump())
        except ValidationError as exc:
            raise DomainError(f"payload inválido: {exc}") from exc
    raise DomainError(f"tipo de payload não suportado: {type(payload)!r}")
