"""Tool `create_pdf_document` — HTML/CSS (WeasyPrint) → PDF.

Pipeline canônico: resolve entrada unificada → `RenderHtmlDocument` +
`WeasyPrintPdfConverter` → ownership fail-closed → `{path, url, metadata}`.
Também aceita `from_preview` (filename ou URL `/api/files/html/...`).
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Union
from urllib.parse import unquote, urlparse

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
from src.infrastructure.documents.weasyprint_pdf_converter import WeasyPrintPdfConverter
from src.infrastructure.ownership.store import record_ownership, resolve_user_id
from src.infrastructure.ownership.session_writers import (
    MissingUserIdentityError,
    require_user_docs_dir,
)
from src.infrastructure.ownership.paths import user_kind_dir
from src.infrastructure.ownership.tool_path_guard import (
    PathNotAuthorizedError,
    authorize_tool_paths,
)
from src.models.html_document_input import HtmlDocumentInput
from src.models.pdf_document import PdfDocumentInput

_PREVIEW_URL_RE = re.compile(
    r"/api/files/html/([^/?#]+\.html)$",
    re.IGNORECASE,
)


def _document_url_prefix() -> str:
    base_url = (
        os.getenv("BASE_URL")
        or os.getenv("FRONTEND_ORIGIN")
        or "http://localhost:3000"
    ).rstrip("/")
    return f"{base_url}/api/files"


def _build_pdf_render(output_dir: Path) -> RenderHtmlDocument:
    return RenderHtmlDocument(
        converters={"pdf": WeasyPrintPdfConverter()},
        output_base_dir=output_dir,
        url_prefix=_document_url_prefix(),
    )


def _preview_filename(ref: str) -> str:
    """Extrai basename seguro de filename ou URL `/api/files/html/...`."""
    raw = ref.strip()
    if not raw:
        raise DomainError("from_preview vazio.")

    match = _PREVIEW_URL_RE.search(urlparse(raw).path if "://" in raw else raw)
    if match:
        name = unquote(match.group(1))
    elif raw.startswith("http://") or raw.startswith("https://") or "/api/files/" in raw:
        path = urlparse(raw).path if "://" in raw else raw
        match = _PREVIEW_URL_RE.search(path)
        if not match:
            raise DomainError(
                "from_preview URL deve apontar para /api/files/html/<arquivo>.html"
            )
        name = unquote(match.group(1))
    else:
        # Filename bare — rejeita qualquer path relativo/absoluto.
        if ".." in raw or "/" in raw or "\\" in raw:
            raise DomainError(f"from_preview inválido: {ref!r}")
        name = raw

    if (
        not name
        or name != Path(name).name
        or ".." in name
        or "/" in name
        or "\\" in name
        or not name.lower().endswith(".html")
    ):
        raise DomainError(f"from_preview inválido: {ref!r}")
    return name


async def _current_user_owns_preview(filename: str) -> bool:
    """True se o user_key do run é dono do HTML em generated_files."""
    user_id = await resolve_user_id()
    if user_id is None:
        return False

    from src.infrastructure.auth.db import get_pool

    pool = get_pool()
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT user_id FROM generated_files "
            "WHERE kind = %s AND filename = %s",
            ("html", filename),
        )
        row = await cur.fetchone()
    return row is not None and str(row[0]) == user_id


async def _load_preview_html(from_preview: str) -> str:
    """Carrega HTML de preview autorizado; DomainError se inválido/não authorized."""
    filename = _preview_filename(from_preview)
    if not await _current_user_owns_preview(filename):
        raise DomainError(
            "Preview HTML não encontrado ou sem permissão para o usuário atual."
        )

    user_id = await resolve_user_id()
    if user_id is None:
        raise DomainError(
            "Preview HTML não encontrado ou sem permissão para o usuário atual."
        )
    # Path derivado do owner resolvido — nunca lê `files/<outro>/` (REQ-004).
    path = user_kind_dir(user_id, "html") / filename
    if not path.is_file():
        raise DomainError(f"Arquivo de preview não encontrado: {filename}")
    return path.read_text(encoding="utf-8")


@tool
async def create_pdf_document(
    payload: Union[str, HtmlDocumentInput, PdfDocumentInput],
) -> dict:
    """Cria um documento PDF (.pdf) a partir de HTML/CSS, template, blocos ou preview.

    Pipeline canônico: HTML → WeasyPrint (não fpdf2). Aceita:
    - `HtmlDocumentInput` (`html` | `template`+`data` | `title`+`blocks`)
    - `from_preview`: filename sob `documents/html/` ou URL `/api/files/html/...`
      owned pelo usuário (finalize sem reenviar o HTML)
    - legado `PdfDocumentInput` (title+blocks)

    Devolve `{path, url, metadata}` com `metadata.kind=\"pdf\"`. Use `url` no markdown.

    Para propostas, prefira `preview_html_document` antes e só então esta tool
    com `from_preview`. String simples não-JSON é rejeitada. Falha de ownership
    é fail-closed.
    """
    try:
        parsed = parse_tool_payload(payload)
    except (DomainError, ValidationError) as exc:
        return {"error": f"Entrada inválida: {exc}"}

    try:
        if parsed.from_preview and parsed.from_preview.strip():
            html = await _load_preview_html(parsed.from_preview)
            css = None
            title = parsed.title
        else:
            templates = FilesystemHtmlTemplateRepository()
            resolved = resolve_html_document_input(
                parsed,
                render_template=templates.render,
            )
            html = resolved.html
            css = resolved.css
            title = resolved.title
    except DomainError as exc:
        return {"error": f"Entrada inválida: {exc}"}
    except ValidationError as exc:
        return {"error": f"Entrada inválida: {exc}"}

    image_paths = [
        b.path
        for b in (parsed.blocks or [])
        if getattr(b, "type", None) == "image" and getattr(b, "path", None)
    ]
    try:
        await authorize_tool_paths(image_paths)
    except (PathNotAuthorizedError, MissingUserIdentityError) as exc:
        return {"error": str(exc)}

    try:
        output_dir = await require_user_docs_dir()
    except MissingUserIdentityError as exc:
        return {"error": str(exc)}

    use_case = _build_pdf_render(output_dir)
    try:
        result = await use_case.execute(
            html=html,
            css=css,
            kind="pdf",
            title=title,
        )
    except DomainError as exc:
        return {"error": f"Entrada inválida: {exc}"}
    except Exception as exc:  # noqa: BLE001 — falha do motor PDF
        return {"error": f"Falha ao gerar PDF: {exc}"}

    try:
        await record_ownership(kind="pdf", filename=Path(result.path).name)
    except Exception as exc:  # noqa: BLE001 — fail-closed para o agente
        return {"error": f"Falha ao registrar ownership: {exc}"}

    return {"path": result.path, "url": result.url, "metadata": result.metadata}
