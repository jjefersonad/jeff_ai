"""Tool `create_pdf_document` — adapter fino sobre o caso de uso `CreateDocument`.

Borda deepagents: traduz a entrada (string JSON ou `PdfDocumentInput`) para
o domínio `PdfSpec`, delega ao caso de uso via `PdfWriter`, carimba ownership
e devolve `{path, url, metadata}`.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Union

from langchain_core.tools import tool
from pydantic import ValidationError

from src.composition.dependencies import build_create_document
from src.domain.documents import (
    Heading,
    ImageRef,
    ListBlock,
    Paragraph,
    PdfSpec,
    Table,
)
from src.domain.shared.errors import DomainError
from src.infrastructure.documents.pdf_writer import PdfWriter
from src.infrastructure.ownership.store import record_ownership
from src.models.pdf_document import PdfBlockInput, PdfDocumentInput


def _to_blocks(raw_blocks: list[PdfBlockInput]) -> tuple[object, ...]:
    """Convert blocks to domain value objects (tipos desconhecidos ignorados)."""
    rendered: list[object] = []
    for block in raw_blocks:
        kind = block.type
        if kind == "heading":
            if not block.text:
                continue
            rendered.append(Heading(text=block.text, level=block.level or 1))
        elif kind == "paragraph":
            if not block.text:
                continue
            rendered.append(Paragraph(text=block.text))
        elif kind == "list":
            if not block.items:
                continue
            rendered.append(
                ListBlock(items=tuple(block.items), ordered=bool(block.ordered)),
            )
        elif kind == "table":
            if not block.rows:
                continue
            rendered.append(
                Table(
                    rows=tuple(tuple(row) for row in block.rows),
                    header=bool(block.header) if block.header is not None else True,
                ),
            )
        elif kind == "image":
            if not block.path:
                continue
            rendered.append(
                ImageRef(path=block.path, width_inches=block.width_inches),
            )
    return tuple(rendered)


def _to_pdf_spec(payload: Union[str, PdfDocumentInput]) -> PdfSpec:
    """Constrói o `PdfSpec` a partir da entrada (string JSON ou input estruturado)."""
    if isinstance(payload, str):
        stripped = payload.strip()
        if stripped.startswith("{"):
            try:
                parsed = json.loads(stripped)
                payload = PdfDocumentInput.model_validate(parsed)
            except (json.JSONDecodeError, ValidationError) as exc:
                raise DomainError(f"payload JSON inválido: {exc}") from exc
        else:
            raise DomainError(
                "Entrada string simples requer conteúdo estruturado (blocks); "
                "use PdfDocumentInput ou um JSON serializado."
            )
    return PdfSpec(title=payload.title, blocks=_to_blocks(payload.blocks))


def _document_url_prefix() -> str:
    base_url = (
        os.getenv("BASE_URL")
        or os.getenv("FRONTEND_ORIGIN")
        or "http://localhost:3000"
    ).rstrip("/")
    return f"{base_url}/api/files"


@tool
async def create_pdf_document(
    payload: Union[str, PdfDocumentInput],
) -> dict:
    """Cria um documento PDF (.pdf) a partir de um título e blocos estruturados.

    Gera o `.pdf` usando apenas a biblioteca Python `fpdf2` (sem `pandoc`,
    `soffice` ou Node) e devolve um dicionário com o mesmo contrato de
    `create_docx_document` / `create_image_from_prompt`:
    - path: caminho local no filesystem (uso interno — NÃO mostrar ao usuário).
    - url: URL servida para download — SEMPRE usar em markdown para exibir o link.
    - metadata: metadados do documento gerado (kind, título, contagem de blocos).

    Requer conteúdo estruturado — SEMPRE envie `PdfDocumentInput` (Pydantic)
    com `title` e `blocks` não vazio (heading/paragraph/list/table/image).
    Uma string simples (não-JSON) NÃO é aceita — é rejeitada com `error`.

    Em caso de entrada inválida ou falha ao registrar ownership, retorna
    `{"error": ...}` sem devolver `path`/`url` de sucesso.

    Example return:
    {"path": "/app/backend/outputs/documents/pdf/20260807120000123456.pdf",
     "url": "http://localhost:3000/api/files/pdf/20260807120000123456.pdf",
     "metadata": {"kind": "pdf", "title": "Relatório", "block_count": 3}}
    """
    try:
        spec = _to_pdf_spec(payload)
    except DomainError as exc:
        return {"error": f"Entrada inválida: {exc}"}

    use_case = build_create_document(
        writer=PdfWriter(url_prefix=_document_url_prefix()),
    )
    result = await use_case.execute(spec)

    try:
        await record_ownership(kind="pdf", filename=Path(result.path).name)
    except Exception as exc:  # noqa: BLE001 — fail-closed para o agente
        return {"error": f"Falha ao registrar ownership: {exc}"}

    return {"path": result.path, "url": result.url, "metadata": result.metadata}
