"""Gestão de sessões server-side (tabela `sessions`, Postgres).

Sessão opaca é a estratégia de autenticação escolhida (ver design da mudança
`autenticacao-jwt-rotas-protegidas`): token de alta entropia, revogação por
`DELETE` imediato, sem chave de assinatura a gerir. Usa o pool dedicado de
`src/infrastructure/auth/db.py` (`get_pool()`), aberto no startup de
`webapp.py`, e é reutilizado tanto por `auth_router.py` (login/logout,
task-rest-1) quanto pelo handler `@auth.authenticate` (task
langgraph-auth-1).

`SESSION_COOKIE_NAME` é definido aqui (não em `auth_router.py`) para ser o
único nome de cookie compartilhado entre quem o CRIA (`auth_router.py`,
login) e quem o LÊ (`dependencies.py`, `require_auth`, task-rest-3).
"""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from src.infrastructure.auth.db import get_pool

SESSION_COOKIE_NAME = "session"

_DEFAULT_SESSION_TTL_SECONDS = 3600


def _session_ttl_seconds() -> int:
    """Lê `SESSION_TTL` do ambiente, em segundos (default 3600)."""
    return int(os.environ.get("SESSION_TTL", _DEFAULT_SESSION_TTL_SECONDS))


@dataclass(frozen=True)
class Session:
    """Sessão válida (token não expirado) e o usuário a que pertence."""

    token: str
    user_id: str
    expires_at: datetime


async def create_session(user_id: str) -> str:
    """Cria uma sessão para `user_id` e devolve o token opaco gerado.

    Token com `secrets.token_urlsafe(32)` (≥256 bits de entropia).
    `expires_at = now() + SESSION_TTL`.
    """
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(UTC) + timedelta(seconds=_session_ttl_seconds())

    pool = get_pool()
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "INSERT INTO sessions (token, user_id, expires_at) VALUES (%s, %s, %s)",
            (token, user_id, expires_at),
        )
    return token


async def get_session(token: str) -> Session | None:
    """Devolve a sessão se `token` existir e não estiver expirado; senão `None`."""
    pool = get_pool()
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT token, user_id, expires_at FROM sessions "
            "WHERE token = %s AND expires_at > now()",
            (token,),
        )
        row = await cur.fetchone()

    if row is None:
        return None
    return Session(token=row[0], user_id=str(row[1]), expires_at=row[2])


async def revoke_session(token: str) -> None:
    """Remove a sessão imediatamente — revogação instantânea, sem denylist."""
    pool = get_pool()
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute("DELETE FROM sessions WHERE token = %s", (token,))
