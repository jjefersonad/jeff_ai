"""Tool `create_xlsx_spreadsheet` — HTML/CSS → XLSX via pipeline.

Pipeline canônico: resolve entrada unificada (ou sheets legados → HTML) →
`RenderHtmlDocument` + `HtmlXlsxConverter` → ownership fail-closed →
`{path, url, metadata}`.
"""
from __future__ import annotations

import html as html_lib
import os
from pathlib import Path
from typing import Union

from langchain_core.tools import tool
from pydantic import ValidationError

from src.application.documents.resolve_html_document_input import (
    parse_tool_payload,
    resolve_html_document_input,
)
from src.application.use_cases.render_html_document import RenderHtmlDocument
from src.domain.shared.errors import DomainError
from src.infrastructure.documents.html_template_repository import (
    FilesystemHtmlTemplateRepository,
)
from src.infrastructure.documents.html_xlsx_converter import HtmlXlsxConverter
from src.infrastructure.ownership.store import record_ownership
from src.infrastructure.ownership.session_writers import (
    MissingUserIdentityError,
    require_user_docs_dir,
)
from src.models.html_document_input import HtmlDocumentInput
from src.models.xlsx_document import XlsxDocumentInput, XlsxSheetInput


def _document_url_prefix() -> str:
    base_url = (
        os.getenv("BASE_URL")
        or os.getenv("FRONTEND_ORIGIN")
        or "http://localhost:3000"
    ).rstrip("/")
    return f"{base_url}/api/files"


def _build_xlsx_render(output_dir: Path) -> RenderHtmlDocument:
    return RenderHtmlDocument(
        converters={"xlsx": HtmlXlsxConverter()},
        output_base_dir=output_dir,
        url_prefix=_document_url_prefix(),
    )


def _escape(text: object) -> str:
    return html_lib.escape("" if text is None else str(text), quote=True)


def sheets_to_html(sheets: list[XlsxSheetInput]) -> str:
    """Converte abas legadas em HTML com `<table data-sheet-name=...>`."""
    if not sheets:
        raise DomainError("sheets é obrigatório e não pode ficar vazio.")
    parts: list[str] = ['<!DOCTYPE html><html><body>']
    for sheet in sheets:
        name = (sheet.name or "").strip()
        if not name:
            raise DomainError("Nome de aba é obrigatório e não pode ser vazio.")
        rows = sheet.rows or []
        if not rows:
            raise DomainError(
                f"Aba {name!r} sem linhas utilizáveis para XLSX."
            )
        parts.append(f'<table data-sheet-name="{_escape(name)}">')
        for row in rows:
            parts.append("<tr>")
            for cell in row:
                parts.append(f"<td>{_escape(cell)}</td>")
            parts.append("</tr>")
        parts.append("</table>")
    parts.append("</body></html>")
    return "".join(parts)


@tool
async def create_xlsx_spreadsheet(
    payload: Union[str, XlsxDocumentInput, HtmlDocumentInput],
) -> dict:
    """Cria uma planilha (.xlsx) a partir de HTML/CSS, template ou abas.

    Pipeline canônico: HTML com `<table>` → `HtmlXlsxConverter` (openpyxl).
    Aceita `HtmlDocumentInput` (`html` | `template`+`data` | `title`+`blocks`)
    ou o legado `XlsxDocumentInput` (sheets). Devolve `{path, url, metadata}`
    com `metadata.kind=\"xlsx\"` — use `url` no markdown.

    HTML sem tabela utilizável → `{error}` sem arquivo parcial. Falha de
    ownership é fail-closed.
    """
    try:
        if isinstance(payload, XlsxDocumentInput):
            resolved_html = sheets_to_html(payload.sheets)
            title = payload.sheets[0].name if payload.sheets else None
            css = None
        else:
            parsed = parse_tool_payload(payload)
            templates = FilesystemHtmlTemplateRepository()
            resolved = resolve_html_document_input(
                parsed,
                render_template=templates.render,
            )
            resolved_html = resolved.html
            css = resolved.css
            title = resolved.title
    except (DomainError, ValidationError) as exc:
        return {"error": f"Entrada inválida: {exc}"}

    try:
        output_dir = await require_user_docs_dir()
    except MissingUserIdentityError as exc:
        return {"error": str(exc)}

    use_case = _build_xlsx_render(output_dir)
    try:
        result = await use_case.execute(
            html=resolved_html,
            css=css,
            kind="xlsx",
            title=title,
        )
    except DomainError as exc:
        return {"error": f"Entrada inválida: {exc}"}
    except Exception as exc:  # noqa: BLE001 — falha do converter
        return {"error": f"Falha ao gerar XLSX: {exc}"}

    try:
        await record_ownership(kind="xlsx", filename=Path(result.path).name)
    except Exception as exc:  # noqa: BLE001 — fail-closed
        return {"error": f"Falha ao registrar ownership: {exc}"}

    return {"path": result.path, "url": result.url, "metadata": result.metadata}
