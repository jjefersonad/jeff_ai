"""Autorização de path de sessão (session-file-sandbox D4)."""
from __future__ import annotations

from pathlib import Path

from src.infrastructure.auth.db import get_pool
from src.infrastructure.ownership.paths import (
    kind_to_subdir,
    user_files_root,
    user_kind_dir,
    workspace_dir,
)


class PathNotAuthorizedError(PermissionError):
    """Path fora do sandbox da sessão (fail-closed)."""


def _resolved(path: Path) -> Path:
    try:
        return path.resolve()
    except (OSError, ValueError) as exc:
        raise PathNotAuthorizedError(f"invalid path: {path}") from exc


def _is_relative_to(path: Path, base: Path) -> bool:
    try:
        path.relative_to(base)
        return True
    except ValueError:
        return False


async def _owned_under_user_files(path: Path, *, user_id: str) -> bool:
    """True se há ownership coerente com o subdir (`docs`/`images`/`attachment`)."""
    pool = get_pool()
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT 1 FROM chat_attachments "
            "WHERE user_id = %s AND storage_path = %s LIMIT 1",
            (user_id, str(path)),
        )
        if await cur.fetchone() is not None:
            # Anexo de chat só é válido sob attachment/
            return path.parent.name == "attachment" and _is_relative_to(
                path, _resolved(user_kind_dir(user_id, "reference"))
            )

        filename = path.name
        await cur.execute(
            "SELECT kind FROM generated_files "
            "WHERE user_id = %s AND filename = %s",
            (user_id, filename),
        )
        rows = await cur.fetchall()

    for (kind,) in rows:
        try:
            expected_dir = _resolved(user_kind_dir(user_id, kind))
        except ValueError:
            continue
        if _resolved(path.parent) == expected_dir and kind_to_subdir(kind) == path.parent.name:
            return True
    return False


async def authorize_session_path(
    path: str | Path,
    *,
    user_id: str,
    role: str,
    thread_id: str,
) -> None:
    """Fail-closed: permite admin, workspace da thread, ou files/<user_id> owned.

    Raises
    ------
    PathNotAuthorizedError
        Se o path não pertence à sessão.
    """
    resolved = _resolved(Path(path))

    if role == "admin":
        return

    thread_workspace = _resolved(workspace_dir() / thread_id)
    if _is_relative_to(resolved, thread_workspace):
        return

    own_root = _resolved(user_files_root(user_id))
    if _is_relative_to(resolved, own_root):
        if await _owned_under_user_files(resolved, user_id=user_id):
            return
        raise PathNotAuthorizedError(
            f"path not owned by session user: {resolved}"
        )

    # Qualquer outro prefixo (files/<outro>/, outputs legado, REPO_ROOT, …).
    raise PathNotAuthorizedError(f"path outside session sandbox: {resolved}")
