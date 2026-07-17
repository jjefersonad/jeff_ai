"""Rotas HTTP de documentos Office (docx/xlsx/pptx) gerados pelas tools.

Portado 1:1 de `backend/image_server.py` para ser montado como `APIRouter`
pelo `http.app` do backend LangGraph (`src/infrastructure/web/webapp.py`).
"""

import os
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

router = APIRouter()

# Diretório-base dos documentos Office (docx/xlsx/pptx) gerados pelas tools.
# Pode ser sobrescrito por env var em testes (DOCUMENTS_DIR).
DOCUMENTS_DIR = Path(os.environ.get("DOCUMENTS_DIR", "/deps/backend/outputs/documents"))

# Kinds de documento aceitos em /api/files/{kind}/{name}.
# Restringe a superfície da rota: qualquer outro valor retorna 400.
_DOCUMENT_KINDS: frozenset[str] = frozenset({"docx", "xlsx", "pptx"})

# Mime types oficiais do OOXML — servidos com `Content-Disposition: attachment`
# para forçar download em vez de abrir inline no browser.
_DOCUMENT_MEDIA_TYPES: dict[str, str] = {
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}


def _document_kind_dir(kind: str) -> Path | None:
    """Resolve o subdiretório de um kind (docx/xlsx/pptx) ou None se inválido."""
    if kind not in _DOCUMENT_KINDS:
        return None
    return DOCUMENTS_DIR / kind


def _safe_resolve(path: Path, base: Path) -> Path | None:
    """Resolve `path` e devolve None se escapar de `base` (path traversal)."""
    try:
        resolved = path.resolve()
    except (OSError, ValueError):
        return None
    if not str(resolved).startswith(str(base.resolve())):
        return None
    return resolved


@router.get("/api/files/{kind}/{filename}")
async def serve_document(kind: str, filename: str):
    """Serve um documento Office gerado (docx/xlsx/pptx) para download.

    `kind` é restrito a `docx|xlsx|pptx` (qualquer outro valor → 400). O nome do
    arquivo é validado contra path traversal (`..`, separadores). O arquivo
    resolvido deve estar dentro do subdiretório do `kind` em `DOCUMENTS_DIR`;
    caso contrário → 400. Se o arquivo não existir → 404.

    A resposta carrega o `Content-Type` oficial do OOXML e
    `Content-Disposition: attachment` para forçar download no browser.
    """
    # 1. Kind restrito.
    target_dir = _document_kind_dir(kind)
    if target_dir is None:
        raise HTTPException(status_code=400, detail="Invalid document kind")

    # 2. Nome do arquivo: sem traversal, sem separadores, com extensão conhecida.
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    suffix = Path(filename).suffix.lower()
    media_type = _DOCUMENT_MEDIA_TYPES.get(suffix)
    if media_type is None:
        raise HTTPException(status_code=400, detail="Unsupported document type")

    # 3. Path final: resolve e valida que continua dentro de `target_dir`.
    candidate = target_dir / filename
    resolved = _safe_resolve(candidate, target_dir)
    if resolved is None:
        raise HTTPException(status_code=400, detail="Invalid filename")

    if not resolved.exists() or not resolved.is_file():
        raise HTTPException(status_code=404, detail="Document not found")

    return FileResponse(
        path=str(resolved),
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "max-age=3600",
        },
    )
