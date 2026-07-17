"""Resolução de usuário a partir do cookie de sessão — núcleo compartilhado.

Único ponto que lê `PUBLIC_PATHS`, o cookie de sessão e consulta
`sessions`/`users`. Dois pontos de entrada usam esta mesma lógica (REQ-003 de
`langgraph-native-auth-middleware`: "usuário resolvido é o mesmo modelo de
sessão"):
- `dependencies.require_auth` (FastAPI, rotas REST em `webapp.py`, task-rest-3)
- `web.auth.authenticate` (handler nativo do LangGraph, task-langgraph-auth-1)

Cada um traduz `SessionAuthError` para o tipo de exceção HTTP do seu próprio
framework (`fastapi.HTTPException` / `Auth.exceptions.HTTPException`).
"""

from __future__ import annotations

import os

from starlette.requests import Request

from src.infrastructure.auth.sessions import SESSION_COOKIE_NAME, get_session
from src.infrastructure.auth.users import User, get_user_by_id

_DEFAULT_PUBLIC_PATHS = ("/public/",)


class SessionAuthError(Exception):
    """Cookie de sessão ausente, desconhecido, expirado, ou usuário inativo/removido."""


def public_path_prefixes() -> tuple[str, ...]:
    """Lê `PUBLIC_PATHS` do ambiente (lista separada por vírgula; default `/public/`)."""
    raw = os.environ.get("PUBLIC_PATHS")
    if not raw:
        return _DEFAULT_PUBLIC_PATHS
    return tuple(prefix.strip() for prefix in raw.split(",") if prefix.strip())


def is_public_path(path: str) -> bool:
    """Devolve `True` se `path` corresponder a algum prefixo de `PUBLIC_PATHS`."""
    return any(path.startswith(prefix) for prefix in public_path_prefixes())


async def resolve_session_user(request: Request) -> User | None:
    """Devolve o usuário da sessão do cookie, ou `None` se o path é público.

    Levanta `SessionAuthError` se o path não é público e o cookie estiver
    ausente, for desconhecido, expirado, ou apontar para um usuário
    removido/inativo.
    """
    if is_public_path(request.url.path):
        return None

    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        raise SessionAuthError("missing session cookie")

    session = await get_session(token)
    if session is None:
        raise SessionAuthError("unknown or expired session token")

    user = await get_user_by_id(session.user_id)
    if user is None or not user.is_active:
        raise SessionAuthError("session user not found or inactive")

    return user
