"""Helpers fail-closed para writers de `files/<user_id>/…` (session-file-sandbox D5/D8)."""
from __future__ import annotations

from pathlib import Path

from src.infrastructure.ownership.paths import user_kind_dir
from src.infrastructure.ownership.store import resolve_user_id


class MissingUserIdentityError(RuntimeError):
    """Criação de arquivo exige `user_id` resolvível (REQ-007 / D8)."""


async def require_user_id() -> str:
    """Resolve o `user_id` da sessão ou falha fechado."""
    user_id = await resolve_user_id()
    if not user_id:
        raise MissingUserIdentityError(
            "user_id is required to create owned files (no session identity)"
        )
    return user_id


async def require_user_kind_dir(kind: str) -> Path:
    """`files/<user_id>/{docs|images|attachment}` — cria a pasta se precisar."""
    user_id = await require_user_id()
    path = user_kind_dir(user_id, kind)
    path.mkdir(parents=True, exist_ok=True)
    return path


async def require_user_docs_dir() -> Path:
    """Diretório flat de documentos: `files/<user_id>/docs/`."""
    return await require_user_kind_dir("docx")
