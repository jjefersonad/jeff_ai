"""Leitura de usuários (tabela `users`, Postgres).

`get_user_by_username` é usado pelo login (`auth_router.py`, task-rest-1)
para buscar credenciais por username. `get_user_by_id` é usado por
`dependencies.py` (`require_auth`, task-rest-3) para resolver o usuário dono
de uma sessão válida. Ambos usam o pool dedicado de
`src/infrastructure/auth/db.py` (`get_pool()`), o mesmo já reutilizado por
`sessions.py`.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.infrastructure.auth.db import get_pool

_SELECT_FIELDS = "id, username, password_hash, role, is_active"


@dataclass(frozen=True)
class User:
    """Usuário autenticável, com o hash de senha para verificação no login."""

    id: str
    username: str
    password_hash: str
    role: str
    is_active: bool


def _row_to_user(row: tuple) -> User:
    return User(
        id=str(row[0]),
        username=row[1],
        password_hash=row[2],
        role=row[3],
        is_active=row[4],
    )


async def get_user_by_username(username: str) -> User | None:
    """Devolve o usuário com `username`, ou `None` se não existir."""
    pool = get_pool()
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            f"SELECT {_SELECT_FIELDS} FROM users WHERE username = %s",
            (username,),
        )
        row = await cur.fetchone()

    return _row_to_user(row) if row is not None else None


async def get_user_by_id(user_id: str) -> User | None:
    """Devolve o usuário com `id`, ou `None` se não existir."""
    pool = get_pool()
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            f"SELECT {_SELECT_FIELDS} FROM users WHERE id = %s",
            (user_id,),
        )
        row = await cur.fetchone()

    return _row_to_user(row) if row is not None else None
