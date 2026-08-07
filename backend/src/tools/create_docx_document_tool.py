"""Tool `create_docx_document` — HTML/CSS → DOCX via pipeline.

Pipeline canônico: resolve entrada unificada → `RenderHtmlDocument` +
`HtmlDocxConverter` → ownership fail-closed → `{path, url, metadata}`.
"""
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
from src.application.use_cases.render_html_document import RenderHtmlDocument
from src.domain.documents.docx_spec import DocxSpec
from src.domain.documents import Heading, ImageRef, ListBlock, Paragraph, Table
from src.domain.shared.errors import DomainError
from src.infrastructure.documents.html_docx_converter import HtmlDocxConverter
from src.infrastructure.documents.html_template_repository import (
    FilesystemHtmlTemplateRepository,
)
from src.infrastructure.ownership.store import record_ownership
from src.models.docx_document import DocxBlockInput, DocxDocumentInput
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


def _build_docx_render() -> RenderHtmlDocument:
    return RenderHtmlDocument(
        converters={"docx": HtmlDocxConverter()},
        output_base_dir=_documents_base_dir(),
        url_prefix=_document_url_prefix(),
    )


def _to_blocks(raw_blocks: list[DocxBlockInput]) -> tuple[object, ...]:
    """Converte DocxBlockInput → VOs de domínio (validação DocxSpec / markdown)."""
    rendered: list[object] = []
    for block in raw_blocks:
        kind = block.type
        if kind == "heading" and block.text:
            rendered.append(Heading(text=block.text, level=block.level or 1))
        elif kind == "paragraph" and block.text:
            rendered.append(Paragraph(text=block.text))
        elif kind == "list" and block.items:
            rendered.append(
                ListBlock(items=tuple(block.items), ordered=bool(block.ordered)),
            )
        elif kind == "table" and block.rows:
            rendered.append(
                Table(
                    rows=tuple(tuple(row) for row in block.rows),
                    header=bool(block.header) if block.header is not None else True,
                ),
            )
        elif kind == "image" and block.path:
            rendered.append(
                ImageRef(path=block.path, width_inches=block.width_inches),
            )
    return tuple(rendered)


@tool
async def create_docx_document(
    payload: Union[str, DocxDocumentInput, HtmlDocumentInput],
) -> dict:
    """Cria um documento Word (.docx) a partir de HTML/CSS, template ou blocos.

    Pipeline canônico: HTML → `HtmlDocxConverter` (python-docx semântico).
    Aceita `HtmlDocumentInput` (`html` | `template`+`data` | `title`+`blocks`)
    ou o legado `DocxDocumentInput`. Devolve `{path, url, metadata}` com
    `metadata.kind=\"docx\"` — use `url` no markdown.

    Tabelas: use bloco `type=\"table\"` com `rows` (não Markdown `| col |` em
    paragraph). String simples não-JSON é rejeitada. Falha de ownership é
    fail-closed.
    """
    try:
        parsed = parse_tool_payload(payload)
        # Revalida DocxSpec quando há blocks (markdown table + título/blocks).
        if parsed.blocks:
            docx_blocks = [
                DocxBlockInput.model_validate(b.model_dump()) for b in parsed.blocks
            ]
            DocxSpec(
                title=parsed.title or "Documento",
                blocks=_to_blocks(docx_blocks),
            )
        templates = FilesystemHtmlTemplateRepository()
        resolved = resolve_html_document_input(
            parsed,
            render_template=templates.render,
        )
    except (DomainError, ValidationError) as exc:
        return {"error": f"Entrada inválida: {exc}"}

    use_case = _build_docx_render()
    try:
        result = await use_case.execute(
            html=resolved.html,
            css=resolved.css,
            kind="docx",
            title=resolved.title,
        )
    except DomainError as exc:
        return {"error": f"Entrada inválida: {exc}"}
    except Exception as exc:  # noqa: BLE001 — falha do converter
        return {"error": f"Falha ao gerar DOCX: {exc}"}

    try:
        await record_ownership(kind="docx", filename=Path(result.path).name)
    except Exception as exc:  # noqa: BLE001 — fail-closed
        return {"error": f"Falha ao registrar ownership: {exc}"}

    return {"path": result.path, "url": result.url, "metadata": result.metadata}
