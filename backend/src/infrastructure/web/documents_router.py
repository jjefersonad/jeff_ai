"""Rotas HTTP de documentos Office (docx/xlsx/pptx) e diagramas HTML
gerados pelas tools/skills.

Portado 1:1 de `backend/image_server.py` para ser montado como `APIRouter`
pelo `http.app` do backend LangGraph (`src/infrastructure/web/webapp.py`).

REQ-002 de `media-ownership-authorization` (task-media-2): download restrito
ao dono do arquivo (`generated_files`), exceto `role admin`. `require_auth`
já é dependency global do app (`webapp.py`), então o usuário aqui nunca é
`None` na prática — o `User | None` no tipo só reflete a assinatura de
`require_auth`, seguindo o mesmo padrão de `scheduling_router.py`.
"""

import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from src.infrastructure.auth.dependencies import require_auth
from src.infrastructure.auth.users import User
from src.infrastructure.ownership.store import is_authorized

router = APIRouter()

DOCUMENTS_DIR = Path(os.environ.get("DOCUMENTS_DIR", "/deps/backend/outputs/documents"))

_DOCUMENT_KINDS: frozenset[str] = frozenset({"docx", "xlsx", "pptx", "html"})

_DOCUMENT_MEDIA_TYPES: dict[str, str] = {
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".html": "text/html",
}

_ATTACHMENT_KINDS: frozenset[str] = frozenset({"docx", "xlsx", "pptx"})


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


@router.get("/api/files/{kind}/{filename}")
async def serve_document(
    kind: str, filename: str, user: User | None = Depends(require_auth)
):
    if user is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    target_dir = _document_kind_dir(kind)
    if target_dir is None:
        raise HTTPException(status_code=400, detail="Invalid document kind")

    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    suffix = Path(filename).suffix.lower()
    media_type = _DOCUMENT_MEDIA_TYPES.get(suffix)
    if media_type is None:
        raise HTTPException(status_code=400, detail="Unsupported document type")

    candidate = target_dir / filename
    resolved = _safe_resolve(candidate, target_dir)
    if resolved is None:
        raise HTTPException(status_code=400, detail="Invalid filename")

    if not resolved.exists() or not resolved.is_file():
        raise HTTPException(status_code=404, detail="Document not found")

    if not await is_authorized(kind=kind, filename=filename, user=user):
        raise HTTPException(status_code=404, detail="Document not found")

    headers = {"X-Content-Type-Options": "nosniff", "Cache-Control": "max-age=3600"}
    if kind in _ATTACHMENT_KINDS:
        headers["Content-Disposition"] = f'attachment; filename="{filename}"'

    return FileResponse(
        path=str(resolved),
        media_type=media_type,
        headers=headers,
    )