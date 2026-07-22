"""Persistência de anexos de chat: grava os bytes e registra a linha em `chat_attachments`.

Usa o pool compartilhado de `src/infrastructure/auth/db.py` (mesmo pool de
`sessions.py`/`users.py`), aberto no startup do `http.app`. O nome do arquivo
em disco nunca vem do cliente: `attachment_id` é gerado aqui e o `filename`
original é preservado só como metadado na tabela.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

from src.infrastructure.auth.db import get_pool

_CONTENT_TYPE_EXTENSION: dict[str, str] = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/bmp": ".bmp",
    "image/webp": ".webp",
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "text/csv": ".csv",
    "text/plain": ".txt",
}


@dataclass(frozen=True)
class StoredAttachment:
    """Anexo persistido: identidade gerada + metadados registrados em `chat_attachments`."""

    attachment_id: str
    thread_id: str
    filename: str
    content_type: str
    size_bytes: int
    storage_path: str


async def store_attachment(
    *,
    thread_id: str,
    user_id: str,
    data: bytes,
    filename: str,
    content_type: str,
    output_dir: Path,
) -> StoredAttachment:
    """Grava `data` em `{output_dir}/{thread_id}/{attachment_id}.{ext}` e insere a linha em `chat_attachments`."""
    attachment_id = str(uuid.uuid4())
    extension = _CONTENT_TYPE_EXTENSION.get(content_type, ".bin")

    thread_dir = output_dir / thread_id
    thread_dir.mkdir(parents=True, exist_ok=True)
    storage_path = thread_dir / f"{attachment_id}{extension}"
    storage_path.write_bytes(data)

    pool = get_pool()
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "INSERT INTO chat_attachments "
            "(id, thread_id, user_id, filename, content_type, size_bytes, storage_path) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (
                attachment_id,
                thread_id,
                user_id,
                filename,
                content_type,
                len(data),
                str(storage_path),
            ),
        )

    return StoredAttachment(
        attachment_id=attachment_id,
        thread_id=thread_id,
        filename=filename,
        content_type=content_type,
        size_bytes=len(data),
        storage_path=str(storage_path),
    )
