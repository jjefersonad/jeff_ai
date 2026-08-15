"""Tool Tier 1 `list_owned_files` — anexos + gerados do usuário da sessão.

session-owned-file-access REQ-003 / design D7: lista `chat_attachments` e
`generated_files` do `user_id` da sessão (qualquer thread), com filename,
kind/content_type, storage_path derivado e url HTTP. Sem identidade →
fail-closed. `role=admin` MAY listar todos os usuários.
"""
from __future__ import annotations

import json
import os
from typing import Any

from langchain_core.tools import tool

from src.infrastructure.auth.db import get_pool
from src.infrastructure.ownership.paths import resolve_owned_file_path
from src.infrastructure.ownership.store import resolve_user_id

try:
    from langgraph.config import get_config
except ImportError:  # pragma: no cover

    def get_config() -> dict[str, Any]:  # type: ignore[misc]
        return {}


_DOC_KINDS = frozenset({"docx", "xlsx", "pptx", "pdf", "html"})


def _base_url() -> str:
    return (
        os.getenv("BASE_URL")
        or os.getenv("FRONTEND_ORIGIN")
        or "http://localhost:3000"
    ).rstrip("/")


def _resolve_role() -> str:
    try:
        configurable = get_config().get("configurable", {}) or {}
    except Exception:  # noqa: BLE001
        return "user"
    return "admin" if configurable.get("role") == "admin" else "user"


def _url_for_generated(*, kind: str, filename: str) -> str:
    base = _base_url()
    if kind == "image":
        return f"{base}/api/images/{filename}"
    if kind == "reference":
        return f"{base}/api/references/{filename}"
    if kind in _DOC_KINDS:
        return f"{base}/api/files/{kind}/{filename}"
    return f"{base}/api/files/{kind}/{filename}"


def _url_for_attachment(attachment_id: str) -> str:
    return f"{_base_url()}/api/attachments/{attachment_id}"


async def _fetch_rows(*, user_id: str | None, admin_all: bool) -> tuple[list[tuple], list[tuple]]:
    pool = get_pool()
    async with pool.connection() as conn, conn.cursor() as cur:
        if admin_all:
            await cur.execute(
                "SELECT id, user_id, thread_id, filename, content_type, size_bytes, storage_path "
                "FROM chat_attachments ORDER BY created_at DESC NULLS LAST, id"
            )
        else:
            await cur.execute(
                "SELECT id, user_id, thread_id, filename, content_type, size_bytes, storage_path "
                "FROM chat_attachments WHERE user_id = %s "
                "ORDER BY created_at DESC NULLS LAST, id",
                (user_id,),
            )
        attachments = await cur.fetchall()

        if admin_all:
            await cur.execute(
                "SELECT user_id, kind, filename FROM generated_files "
                "ORDER BY created_at DESC NULLS LAST, filename"
            )
        else:
            await cur.execute(
                "SELECT user_id, kind, filename FROM generated_files WHERE user_id = %s "
                "ORDER BY created_at DESC NULLS LAST, filename",
                (user_id,),
            )
        generated = await cur.fetchall()
    return list(attachments), list(generated)


@tool
async def list_owned_files() -> str:
    """Lista anexos e arquivos gerados do usuário da sessão (qualquer thread).

    Devolve JSON com filename, kind/content_type, storage_path e url HTTP —
    use `storage_path` ao passar paths para tools de documento/imagem, e `url`
    no markdown para o usuário. Não lista código do produto nem arquivos de
    outros usuários (exceto sessão admin).
    """
    user_id = await resolve_user_id()
    if not user_id:
        return (
            "ERRO: identidade de usuário não resolvível. "
            "Autentique-se / vincule o canal antes de listar arquivos."
        )

    role = _resolve_role()
    admin_all = role == "admin"
    attachments, generated = await _fetch_rows(user_id=user_id, admin_all=admin_all)

    items: list[dict[str, Any]] = []
    for row in attachments:
        attachment_id, owner_id, _thread_id, filename, content_type, _size, storage_path = row
        items.append(
            {
                "filename": str(filename),
                "kind": "attachment",
                "content_type": str(content_type),
                "storage_path": str(storage_path),
                "url": _url_for_attachment(str(attachment_id)),
                "owner_user_id": str(owner_id),
            }
        )

    for row in generated:
        owner_id, kind, filename = str(row[0]), str(row[1]), str(row[2])
        try:
            path = resolve_owned_file_path(
                user_id=owner_id, kind=kind, filename=filename
            )
        except ValueError:
            continue
        items.append(
            {
                "filename": filename,
                "kind": kind,
                "content_type": kind,
                "storage_path": str(path),
                "url": _url_for_generated(kind=kind, filename=filename),
                "owner_user_id": owner_id,
            }
        )

    if not items:
        return "[]"
    return json.dumps(items, ensure_ascii=False)


__all__ = ["list_owned_files"]
