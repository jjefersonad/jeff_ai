"""Helpers para tools chamarem `authorize_session_path` com o config do run."""
from __future__ import annotations

from collections.abc import Iterable

from langgraph.config import get_config

from src.infrastructure.ownership.path_guard import (
    PathNotAuthorizedError,
    authorize_session_path,
)
from src.infrastructure.ownership.session_writers import (
    MissingUserIdentityError,
    require_user_id,
)


def _get_configurable() -> dict:
    try:
        return get_config().get("configurable", {}) or {}
    except RuntimeError:
        return {}


def _session_role_and_thread() -> tuple[str, str]:
    configurable = _get_configurable()
    role = configurable.get("role") or "user"
    thread_id = configurable.get("thread_id") or ""
    return str(role), str(thread_id)


async def authorize_tool_paths(paths: Iterable[str]) -> None:
    """Autoriza cada path (não-vazio) para a sessão corrente.

    `role=admin` bypass. Sem `user_id` resolvível (e role≠admin) → fail-closed.
    """
    cleaned = [p.strip() for p in paths if isinstance(p, str) and p.strip()]
    if not cleaned:
        return

    role, thread_id = _session_role_and_thread()
    if role == "admin":
        return

    user_id = await require_user_id()
    for path in cleaned:
        await authorize_session_path(
            path,
            user_id=user_id,
            role=role,
            thread_id=thread_id,
        )


__all__ = [
    "MissingUserIdentityError",
    "PathNotAuthorizedError",
    "authorize_tool_paths",
]
