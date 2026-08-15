"""Rotas HTTP de documentos (docx/xlsx/pptx/pdf) e diagramas HTML
gerados pelas tools/skills.

Portado 1:1 de `backend/image_server.py` para ser montado como `APIRouter`
pelo `http.app` do backend LangGraph (`src/infrastructure/web/webapp.py`).

REQ-002 de `media-ownership-authorization` (task-media-2): download restrito
ao dono do arquivo (`generated_files`), exceto `role admin`. `require_auth`
já é dependency global do app (`webapp.py`), então o usuário aqui nunca é
`None` na prática — o `User | None` no tipo só reflete a assinatura de
`require_auth`, seguindo o mesmo padrão de `scheduling_router.py`.

session-file-sandbox (D12/D13): path físico derivado de
`files/<owner>/docs/<filename>`; fallback legado sob `outputs/documents/`
só para `role=admin`.
"""

import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from src.infrastructure.auth.dependencies import require_auth
from src.infrastructure.auth.users import User
from src.infrastructure.ownership.paths import resolve_owned_file_path
from src.infrastructure.ownership.store import get_file_owner, is_authorized

router = APIRouter()

DOCUMENTS_DIR = Path(os.environ.get("DOCUMENTS_DIR", "/deps/backend/outputs/documents"))

_DOCUMENT_KINDS: frozenset[str] = frozenset({"docx", "xlsx", "pptx", "html", "pdf"})

_DOCUMENT_MEDIA_TYPES: dict[str, str] = {
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".html": "text/html",
    ".pdf": "application/pdf",
}

_ATTACHMENT_KINDS: frozenset[str] = frozenset({"docx", "xlsx", "pptx", "pdf"})


def _document_kind_dir(kind: str) -> Path | None:
    if kind not in _DOCUMENT_KINDS:
        return None
    return DOCUMENTS_DIR / kind


def _safe_resolve(path: Path, base: Path) -> Path | None:
    try:
        resolved = path.resolve()
    except (OSError, ValueError):
        return None
    if not str(resolved).startswith(str(base.resolve())):
        return None
    return resolved


def _resolve_document_path(
    *, kind: str, filename: str, owner_id: str | None, role: str
) -> Path | None:
    """Path derivado `files/<owner>/docs/` first; admin MAY fallback to legacy."""
    if owner_id:
        try:
            derived = resolve_owned_file_path(
                user_id=owner_id, kind=kind, filename=filename
            )
        except ValueError:
            derived = None
        if derived is not None:
            base = derived.parent
            resolved = _safe_resolve(derived, base)
            if resolved is not None and resolved.is_file():
                return resolved

    if role == "admin":
        target_dir = _document_kind_dir(kind)
        if target_dir is None:
            return None
        resolved = _safe_resolve(target_dir / filename, target_dir)
        if resolved is not None and resolved.is_file():
            return resolved

    return None


@router.get("/api/files/{kind}/{filename}")
async def serve_document(
    kind: str, filename: str, user: User | None = Depends(require_auth)
):
    if user is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    if kind not in _DOCUMENT_KINDS:
        raise HTTPException(status_code=400, detail="Invalid document kind")

    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    suffix = Path(filename).suffix.lower()
    media_type = _DOCUMENT_MEDIA_TYPES.get(suffix)
    if media_type is None:
        raise HTTPException(status_code=400, detail="Unsupported document type")

    if not await is_authorized(kind=kind, filename=filename, user=user):
        raise HTTPException(status_code=404, detail="Document not found")

    owner_id = await get_file_owner(kind=kind, filename=filename)
    resolved = _resolve_document_path(
        kind=kind, filename=filename, owner_id=owner_id, role=user.role
    )
    if resolved is None:
        raise HTTPException(status_code=404, detail="Document not found")

    headers = {"X-Content-Type-Options": "nosniff", "Cache-Control": "max-age=3600"}
    if kind in _ATTACHMENT_KINDS:
        headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    elif kind == "html":
        # Preview-first: iframe/browser must open HTML inline, not download.
        headers["Content-Disposition"] = f'inline; filename="{filename}"'

    return FileResponse(
        path=str(resolved),
        media_type=media_type,
        headers=headers,
    )