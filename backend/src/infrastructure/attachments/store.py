"""Persistência de anexos de chat: grava os bytes e registra a linha em `chat_attachments`.

Usa o pool compartilhado de `src/infrastructure/auth/db.py` (mesmo pool de
`sessions.py`/`users.py`), aberto no startup do `http.app`. O nome do arquivo
em disco nunca vem do cliente: `attachment_id` é gerado aqui e o `filename`
original é preservado só como metadado na tabela.

Layout (session-file-sandbox D5): `files/<user_id>/attachment/<id>.<ext>`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

from src.infrastructure.auth.db import get_pool
from src.infrastructure.ownership.paths import user_kind_dir
from src.infrastructure.ownership.session_writers import MissingUserIdentityError

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


@dataclass(frozen=True)
class AttachmentRecord:
    """Linha completa de `chat_attachments` (inclui `user_id` para ownership HTTP)."""

    attachment_id: str
    user_id: str
    thread_id: str
    filename: str
    content_type: str
    size_bytes: int
    storage_path: str


async def get_attachment(*, attachment_id: str) -> AttachmentRecord | None:
    """Carrega um anexo por id. `None` se inexistente."""
    pool = get_pool()
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT id, user_id, thread_id, filename, content_type, size_bytes, storage_path "
            "FROM chat_attachments WHERE id = %s",
            (attachment_id,),
        )
        row = await cur.fetchone()
    if row is None:
        return None
    return AttachmentRecord(
        attachment_id=str(row[0]),
        user_id=str(row[1]),
        thread_id=str(row[2]),
        filename=str(row[3]),
        content_type=str(row[4]),
        size_bytes=int(row[5]),
        storage_path=str(row[6]),
    )


async def load_attachments(
    ids: list[str],
    *,
    thread_id: str,
    user_id: str,
) -> list[StoredAttachment | None]:
    """Carrega anexos isolados por `thread_id` **e** `user_id` (REQ-002).

    Preserva a ordem de `ids`. Id inexistente, de outra thread ou de outro
    usuário devolve `None` nesse slot — sem vazar `storage_path`.
    """
    if not ids:
        return []

    pool = get_pool()
    results: list[StoredAttachment | None] = []
    async with pool.connection() as conn, conn.cursor() as cur:
        for attachment_id in ids:
            await cur.execute(
                "SELECT id, user_id, thread_id, filename, content_type, size_bytes, storage_path "
                "FROM chat_attachments "
                "WHERE id = %s AND thread_id = %s AND user_id = %s",
                (attachment_id, thread_id, user_id),
            )
            row = await cur.fetchone()
            if row is None:
                results.append(None)
                continue
            results.append(
                StoredAttachment(
                    attachment_id=str(row[0]),
                    thread_id=str(row[2]),
                    filename=str(row[3]),
                    content_type=str(row[4]),
                    size_bytes=int(row[5]),
                    storage_path=str(row[6]),
                )
            )
    return results


async def store_attachment(
    *,
    thread_id: str,
    user_id: str,
    data: bytes,
    filename: str,
    content_type: str,
    output_dir: Path | None = None,
) -> StoredAttachment:
    """Grava `data` em `files/<user_id>/attachment/{id}.{ext}` e insere em `chat_attachments`.

    `output_dir`, se passado, é ignorado no layout novo (mantido só por
    compatibilidade de assinatura com callers/testes legados) — o destino
    canônico é sempre `user_kind_dir(user_id, \"reference\")` (= attachment/).
    """
    if not user_id:
        raise MissingUserIdentityError(
            "user_id is required to store attachments (no session identity)"
        )

    attachment_id = str(uuid.uuid4())
    extension = _CONTENT_TYPE_EXTENSION.get(content_type, ".bin")

    dest_dir = user_kind_dir(user_id, "reference")
    dest_dir.mkdir(parents=True, exist_ok=True)
    storage_path = dest_dir / f"{attachment_id}{extension}"
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
