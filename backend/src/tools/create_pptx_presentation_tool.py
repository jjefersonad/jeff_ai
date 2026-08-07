"""Tool `create_pptx_presentation` — HTML/CSS → PPTX via pipeline.

Pipeline canônico: resolve entrada unificada (ou slides legados → HTML) →
`RenderHtmlDocument` + `HtmlPptxConverter` → ownership fail-closed →
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
from src.infrastructure.documents.html_pptx_converter import HtmlPptxConverter
from src.infrastructure.documents.html_template_repository import (
    FilesystemHtmlTemplateRepository,
)
from src.infrastructure.ownership.store import record_ownership
from src.models.html_document_input import HtmlDocumentInput
from src.models.pptx_document import PptxDocumentInput, PptxSlideInput

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


def _build_pptx_render() -> RenderHtmlDocument:
    return RenderHtmlDocument(
        converters={"pptx": HtmlPptxConverter()},
        output_base_dir=_documents_base_dir(),
        url_prefix=_document_url_prefix(),
    )


def _escape(text: object) -> str:
    return html_lib.escape("" if text is None else str(text), quote=True)


def slides_to_html(slides: list[PptxSlideInput]) -> str:
    """Converte slides legados em HTML com `section.slide`."""
    if not slides:
        raise DomainError("slides é obrigatório e não pode ficar vazio.")

    parts: list[str] = ['<!DOCTYPE html><html><body>']
    emitted = 0
    for raw in slides:
        kind = (raw.type or "").strip().lower()
        if kind == "title":
            if not raw.title:
                continue
            parts.append('<section class="slide">')
            parts.append(f"<h1>{_escape(raw.title)}</h1>")
            if raw.subtitle:
                parts.append(f"<p>{_escape(raw.subtitle)}</p>")
            parts.append("</section>")
            emitted += 1
        elif kind == "bullets":
            if not raw.title or not raw.bullets:
                continue
            parts.append('<section class="slide">')
            parts.append(f"<h2>{_escape(raw.title)}</h2>")
            parts.append("<ul>")
            for item in raw.bullets:
                parts.append(f"<li>{_escape(item)}</li>")
            parts.append("</ul></section>")
            emitted += 1
        elif kind == "table":
            if not raw.rows:
                continue
            parts.append('<section class="slide">')
            title = raw.title or "Tabela"
            parts.append(f"<h2>{_escape(title)}</h2>")
            parts.append("<table>")
            for row in raw.rows:
                parts.append("<tr>")
                for cell in row:
                    parts.append(f"<td>{_escape(cell)}</td>")
                parts.append("</tr>")
            parts.append("</table></section>")
            emitted += 1
        elif kind == "image":
            # Sem raster no HTML→PPTX v1: slide só com título se houver.
            if not raw.title:
                continue
            parts.append('<section class="slide">')
            parts.append(f"<h2>{_escape(raw.title)}</h2>")
            parts.append("</section>")
            emitted += 1
        # tipo desconhecido: ignorado (contrato tolerante)

    parts.append("</body></html>")
    if emitted == 0:
        raise DomainError("Nenhum slide válido para converter para PPTX.")
    return "".join(parts)


@tool
async def create_pptx_presentation(
    payload: Union[str, PptxDocumentInput, HtmlDocumentInput],
) -> dict:
    """Cria uma apresentação (.pptx) a partir de HTML/CSS, template ou slides.

    Pipeline canônico: HTML com `section.slide` / `div.slide` →
    `HtmlPptxConverter` (python-pptx). Aceita `HtmlDocumentInput`
    (`html` | `template`+`data` | `title`+`blocks`) ou o legado
    `PptxDocumentInput` (slides). Devolve `{path, url, metadata}` com
    `metadata.kind=\"pptx\"` — use `url` no markdown.

    HTML sem slides utilizáveis → `{error}` sem arquivo parcial. Falha de
    ownership é fail-closed.
    """
    try:
        if isinstance(payload, PptxDocumentInput):
            resolved_html = slides_to_html(payload.slides)
            title = None
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

    use_case = _build_pptx_render()
    try:
        result = await use_case.execute(
            html=resolved_html,
            css=css,
            kind="pptx",
            title=title,
        )
    except DomainError as exc:
        return {"error": f"Entrada inválida: {exc}"}
    except Exception as exc:  # noqa: BLE001 — falha do converter
        return {"error": f"Falha ao gerar PPTX: {exc}"}

    try:
        await record_ownership(kind="pptx", filename=Path(result.path).name)
    except Exception as exc:  # noqa: BLE001 — fail-closed
        return {"error": f"Falha ao registrar ownership: {exc}"}

    return {"path": result.path, "url": result.url, "metadata": result.metadata}
