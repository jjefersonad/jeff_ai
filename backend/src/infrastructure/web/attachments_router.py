"""Rota HTTP de anexos de chat (upload) — validação de conteúdo + persistência.

Espelha a estrutura de `images_router.py`/`upload_reference`: recebe o arquivo,
sniffa os bytes reais e o tamanho antes de aceitar. Não confia em extensão ou
Content-Type declarados pelo cliente. `user_id` vem da sessão resolvida por
`require_auth` (dependency global do app, task-backend-upload-3) — nunca do
corpo da requisição.

`GET /api/attachments/{id}` (session-file-sandbox REQ-004): auth + ownership;
lê `storage_path` da linha; 404 para não-dono / inexistente.
"""

from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from src.infrastructure.attachments.store import get_attachment, store_attachment
from src.infrastructure.auth.dependencies import require_auth
from src.infrastructure.auth.users import User
from src.infrastructure.media.attachment_validation import (
    AttachmentValidationError,
    enforce_size_limit,
    sniff_and_validate,
)

router = APIRouter()

_MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024  # 10 MB


@router.post("/api/attachments")
async def upload_attachment(
    file: UploadFile = File(...),
    thread_id: str = Form(...),
    user: User | None = Depends(require_auth),
):
    """Recebe um anexo de chat, valida seu conteúdo real e tamanho, e persiste.

    Aceita imagem, PDF, DOCX, XLSX, CSV e TXT — detectados pelos bytes reais
    do arquivo, não pela extensão ou Content-Type declarados. Recusa conteúdo
    que não corresponda a nenhum formato suportado ou que exceda o tamanho
    máximo configurado. Em sucesso, grava em `files/<user_id>/attachment/` e
    registra a linha em `chat_attachments`.
    """
    if user is None:
        raise HTTPException(status_code=401, detail="Unauthorized")

    data = await file.read()
    try:
        enforce_size_limit(len(data), max_bytes=_MAX_ATTACHMENT_BYTES)
        content_type = sniff_and_validate(data, declared_filename=file.filename or "")
    except AttachmentValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    stored = await store_attachment(
        thread_id=thread_id,
        user_id=user.id,
        data=data,
        filename=file.filename or "",
        content_type=content_type,
    )

    return {
        "attachment_id": stored.attachment_id,
        "url": f"/api/attachments/{stored.attachment_id}",
        "metadata": {
            "thread_id": stored.thread_id,
            "filename": stored.filename,
            "content_type": stored.content_type,
            "size_bytes": stored.size_bytes,
        },
    }


@router.get("/api/attachments/{attachment_id}")
async def download_attachment(
    attachment_id: str,
    user: User | None = Depends(require_auth),
):
    """Serve bytes do anexo se o caller for o dono (admin MAY bypass)."""
    if user is None:
        raise HTTPException(status_code=401, detail="Unauthorized")

    record = await get_attachment(attachment_id=attachment_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Attachment not found")

    if user.role != "admin" and record.user_id != user.id:
        raise HTTPException(status_code=404, detail="Attachment not found")

    path = Path(record.storage_path)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Attachment not found")

    return FileResponse(
        path=str(path),
        media_type=record.content_type,
        headers={
            "Cache-Control": "private, max-age=3600",
            "X-Content-Type-Options": "nosniff",
        },
    )
