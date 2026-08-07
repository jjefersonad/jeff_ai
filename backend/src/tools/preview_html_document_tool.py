"""Tool `preview_html_document` — HTML preview persistido antes do arquivo final."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Union

from langchain_core.tools import tool
from pydantic import ValidationError

from src.application.documents.resolve_html_document_input import (
    parse_tool_payload,
    resolve_html_document_input,
)
from src.application.use_cases.preview_html_document import PreviewHtmlDocument
from src.domain.shared.errors import DomainError
from src.infrastructure.documents.html_template_repository import (
    FilesystemHtmlTemplateRepository,
)
from src.infrastructure.ownership.store import record_ownership
from src.models.html_document_input import HtmlDocumentInput

# backend/outputs/documents
_DEFAULT_DOCUMENTS = Path(__file__).resolve().parents[2] / "outputs" / "documents"


def _documents_base_dir() -> Path:
    env = os.environ.get("DOCUMENTS_DIR")
    if env:
        return Path(env)
    return _DEFAULT_DOCUMENTS


def _document_url_prefix() -> str:
    base_url = (
        os.getenv("BASE_URL")
        or os.getenv("FRONTEND_ORIGIN")
        or "http://localhost:3000"
    ).rstrip("/")
    return f"{base_url}/api/files"


@tool
async def preview_html_document(
    payload: Union[str, HtmlDocumentInput],
) -> dict:
    """Gera um preview HTML servível no web antes do PDF/Office final.

    Resolve a entrada unificada (`html` | `template`+`data` | `title`+`blocks`),
    sanitiza, embute CSS e grava em `outputs/documents/html/`. Devolve
    `{path, url, metadata}` com `metadata.kind=\"html\"` e `url` em
    `/api/files/html/...` — use essa URL no markdown para o usuário revisar.

    Fluxo recomendado (propostas e documentos estilizados):
    1. Chame esta tool e mostre a `url`.
    2. Itere com novo preview se o usuário pedir ajustes.
    3. Só então chame `create_pdf_document` (ou Office) — preferencialmente
       com `from_preview` apontando para o HTML aprovado.

    Entrada inválida ou falha de ownership retorna `{\"error\": ...}` sem
    `path`/`url` de sucesso.
    """
    try:
        parsed = parse_tool_payload(payload)
        templates = FilesystemHtmlTemplateRepository()
        resolved = resolve_html_document_input(
            parsed,
            render_template=templates.render,
        )
    except (DomainError, ValidationError) as exc:
        return {"error": f"Entrada inválida: {exc}"}

    use_case = PreviewHtmlDocument(
        output_base_dir=_documents_base_dir(),
        url_prefix=_document_url_prefix(),
    )
    try:
        result = use_case.execute(
            html=resolved.html,
            css=resolved.css,
            title=resolved.title,
            template=resolved.template,
        )
    except DomainError as exc:
        return {"error": f"Entrada inválida: {exc}"}

    try:
        await record_ownership(kind="html", filename=Path(result.path).name)
    except Exception as exc:  # noqa: BLE001 — fail-closed para o agente
        return {"error": f"Falha ao registrar ownership: {exc}"}

    return {"path": result.path, "url": result.url, "metadata": result.metadata}
