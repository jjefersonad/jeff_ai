"""Tool `read_document` — leitura de documentos Office e PDF via markitdown.

Substitui a change `document-reading-tools` (que previa 4 readers distintos
em DDD estrito) por uma única tool flat que delega ao `markitdown` da
Microsoft.

Path guard (session-file-sandbox):
- `role=admin`: paths sob `REPO_ROOT` (comportamento legado) **ou** paths
  autorizados pela sessão.
- `role=user`: só workspace da thread / `files/<user_id>/` owned — paths sob
  o source do produto (`REPO_ROOT`) são recusados.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from langchain_core.tools import tool
from langgraph.config import get_config
from markitdown import MarkItDown

from src.infrastructure.ownership.path_guard import PathNotAuthorizedError
from src.infrastructure.ownership.session_writers import (
    MissingUserIdentityError,
    require_user_id,
)
from src.infrastructure.ownership.tool_path_guard import authorize_tool_paths
from src.tools.self_extension import REPO_ROOT, _MAX_READ_CHARS, _within_repo

_log = logging.getLogger(__name__)

_SUPPORTED_EXTS: frozenset[str] = frozenset({
    "docx", "xlsx", "pptx", "pdf",
    "html", "htm", "csv", "json", "xml",
    "md", "markdown", "txt",
})

_OUTPUT_MAX_CHARS: int = _MAX_READ_CHARS


def _session_role() -> str:
    try:
        configurable = get_config().get("configurable", {}) or {}
    except RuntimeError:
        configurable = {}
    return str(configurable.get("role") or "user")


def _resolve_admin(path: str) -> Path | str:
    """Resolve path absoluto/relativo sob REPO_ROOT (legado admin)."""
    if not path or not path.strip():
        return "Caminho vazio."
    p = Path(path)
    if not p.is_absolute():
        p = REPO_ROOT / path
    try:
        p = p.resolve()
    except OSError as e:
        return f"Caminho inválido: {e}"
    if not _within_repo(p):
        return "Acesso negado: caminho fora do repositório."
    if not p.exists():
        return f"Arquivo não encontrado: {path}"
    if not p.is_file():
        return f"Não é um arquivo: {path}"
    return p


# Alias preservado para testes/legado.
_resolve = _resolve_admin


def _detect_format(path: Path) -> str:
    return path.suffix.lower().lstrip(".")


def _truncate(text: str) -> str:
    if len(text) <= _OUTPUT_MAX_CHARS:
        return text
    return (
        text[:_OUTPUT_MAX_CHARS]
        + f"\n\n[...truncado em {_OUTPUT_MAX_CHARS} caracteres. "
        "Use a UI nativa do Office / um viewer para o documento completo.]"
    )


@tool
async def read_document(
    path: str,
    format_hint: Optional[str] = None,
) -> str:
    """Lê um documento (Office, PDF, HTML, CSV, JSON, etc.) e devolve em Markdown.

    `path` absoluto sob `files/<user_id>/` (owned) ou, para `role=admin`,
    relativo a `REPO_ROOT` / absoluto dentro do repositório. Suporta
    `.docx`, `.xlsx`, `.pptx`, `.pdf`, `.html`, `.csv`, `.json`, `.xml`,
    `.md`, `.txt`. Conteúdo convertido para Markdown.

    `format_hint` é opcional; se passado, força o formato (ex.: `"pdf"`).

    Sessões `role=user` não leem source do produto. Erros devolvem string.
    """
    role = _session_role()

    if role == "admin":
        resolved = _resolve_admin(path)
        if isinstance(resolved, str):
            # Admin MAY also ler arquivos owned sob files/ fora do repo.
            try:
                await authorize_tool_paths([path])
            except (PathNotAuthorizedError, MissingUserIdentityError):
                return resolved
            p = Path(path).resolve()
            if not p.is_file():
                return resolved
        else:
            p = resolved
    else:
        try:
            await require_user_id()
            await authorize_tool_paths([path])
        except MissingUserIdentityError as exc:
            return str(exc)
        except PathNotAuthorizedError as exc:
            return f"Acesso negado: {exc}"
        p = Path(path).resolve()
        if not p.is_file():
            return f"Arquivo não encontrado: {path}"

    fmt = (format_hint or _detect_format(p)).lower().lstrip(".")
    if fmt not in _SUPPORTED_EXTS:
        return (
            f"Formato não suportado: .{fmt}. "
            f"Suportados: {', '.join(sorted(_SUPPORTED_EXTS))}."
        )

    try:
        md = MarkItDown()
        result = md.convert(str(p))
    except Exception as e:  # noqa: BLE001 — markitdown
        _log.warning("markitdown falhou para %s: %s", p, e)
        return f"Erro ao ler '{path}': {e}"

    text = result.text_content or ""
    if not text.strip():
        return f"Documento '{path}' está vazio ou não tem texto extraível."

    try:
        rel = p.relative_to(REPO_ROOT)
        label = str(rel)
    except ValueError:
        label = p.name
    header = f"<!-- read_document: {label} ({len(text)} chars) -->\n"
    return _truncate(header + text)
