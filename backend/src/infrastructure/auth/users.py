"""Leitura de usuários (tabela `users`, Postgres).

`get_user_by_username` é usado pelo login (`auth_router.py`, task-rest-1)
para buscar credenciais por username. `get_user_by_id` é usado por
`dependencies.py` (`require_auth`, task-rest-3) para resolver o usuário dono
de uma sessão válida. `list_users` é usado por `admin_users_router`
(`GET /admin/users`, change `user-management`, task-api-1) sob `require_admin`
— por isso devolve TODOS os usuários incluindo inativos; o filtro de campos
sensíveis (ex. `password_hash`) é responsabilidade do response model da API
(REQ-001 do spec `user-management-api`), nunca desta função de dados. Todos
usam o pool dedicado de `src/infrastructure/auth/db.py` (`get_pool()`), o
mesmo já reutilizado por `sessions.py`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.infrastructure.auth.db import get_pool

# `created_at` foi adicionado no resgate de core-2 (dentro de api-1) para
# satisfazer o `UserPublic` da API. `password_hash` continua aqui porque
# `get_user_by_username` precisa dele para o `verify_password` no login;
# a filtragem é responsabilidade da camada HTTP.
_SELECT_FIELDS = "id, username, password_hash, role, is_active, created_at"


@dataclass(frozen=True)
class User:
    """Usuário autenticável, com o hash de senha para verificação no login."""

    id: str
    username: str
    password_hash: str
    role: str
    is_active: bool
    created_at: datetime


def _row_to_user(row: tuple) -> User:
    return User(
        id=str(row[0]),
        username=row[1],
        password_hash=row[2],
        role=row[3],
        is_active=row[4],
        created_at=row[5],
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


async def create_user(username: str, password_hash: str, role: str = "user") -> User:
    """Cria um usuário e devolve a linha inserida (`id`/`created_at` gerados pelo banco).

    Usado por `POST /admin/users` (change `user-management`, task-api-2) sob
    `require_admin`. `password_hash` já deve chegar pronto (`get_password_hash`
    na camada HTTP) — esta função nunca lida com senha em texto plano.
    """
    pool = get_pool()
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (%s, %s, %s) "
            f"RETURNING {_SELECT_FIELDS}",
            (username, password_hash, role),
        )
        row = await cur.fetchone()

    return _row_to_user(row)


class SelfLockoutError(ValueError):
    """`update_user` recusado: o caller tentaria reduzir o próprio acesso."""


class LastAdminError(ValueError):
    """`update_user` recusado: removeria o último `role=admin AND is_active=true` restante."""


async def update_user(
    user_id: str, *, role: str | None = None, is_active: bool | None = None, caller_id: str
) -> User:
    """Atualiza `role`/`is_active` de um usuário, com o guarda-corpo de auto-lockout embutido.

    Usado por `PATCH /admin/users/{id}` (change `user-management`,
    task-core-3/api-3/api-4) sob `require_admin`. Guarda-corpo (design
    Decision "auto-lockout", REQ-004): rejeita ANTES de qualquer `UPDATE`
    quando (a) `user_id == caller_id` e a mudança reduziria o próprio acesso
    (`is_active=False` ou `role="user"`), ou (b) o alvo é o único usuário
    `role="admin" AND is_active=true` restante e a mudança o removeria dessa
    condição. `role`/`is_active` não informados (`None`) mantêm o valor atual.
    """
    would_reduce_access = is_active is False or role == "user"

    if user_id == caller_id and would_reduce_access:
        raise SelfLockoutError(
            f"usuário '{caller_id}' não pode reduzir o próprio acesso via PATCH"
        )

    pool = get_pool()
    async with pool.connection() as conn, conn.cursor() as cur:
        if would_reduce_access:
            await cur.execute("SELECT count(*) FROM users WHERE role = 'admin' AND is_active = true")
            (active_admin_count,) = await cur.fetchone()

            await cur.execute(f"SELECT {_SELECT_FIELDS} FROM users WHERE id = %s", (user_id,))
            target = _row_to_user(await cur.fetchone())

            target_is_active_admin = target.role == "admin" and target.is_active
            if target_is_active_admin and active_admin_count <= 1:
                raise LastAdminError(
                    f"usuário '{user_id}' é o último admin ativo — mudança recusada"
                )

        set_clauses: list[str] = []
        params: list[str | bool] = []
        if role is not None:
            set_clauses.append("role = %s")
            params.append(role)
        if is_active is not None:
            set_clauses.append("is_active = %s")
            params.append(is_active)
        params.append(user_id)

        await cur.execute(
            f"UPDATE users SET {', '.join(set_clauses)} WHERE id = %s RETURNING {_SELECT_FIELDS}",
            tuple(params),
        )
        row = await cur.fetchone()

    return _row_to_user(row)


async def list_users() -> list[User]:
    """Devolve todos os usuários (incluindo inativos), ordenados por `created_at`.

    Lista sem `WHERE`: o filtro de inativos acontece no momento do login via
    `is_active` em `resolve_session_user`, e o endpoint `GET /admin/users`
    precisa enxergar todos os registros para a tela de gestão. A ordem
    determinística evita que o `GET` retorne ordens diferentes entre
    requisições, o que faria a UI piscar ao recarregar.
    """
    pool = get_pool()
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            f"SELECT {_SELECT_FIELDS} FROM users ORDER BY created_at ASC, id ASC"
        )
        rows = await cur.fetchall()

    return [_row_to_user(row) for row in rows]
