"""Pool de conexão Postgres dedicado ao módulo de autenticação.

Não há um `db_pool` compartilhado no processo `http.app` (o antigo
`server.py`, que teria um, não existe mais — ver design da mudança
`autenticacao-jwt-rotas-protegidas`). Este pool é próprio do módulo de auth,
aberto no evento de startup do `FastAPI` em `webapp.py` (`init_pool`) e
reutilizado por `sessions.py` (task auth-core-3), `users.py` (task
rest-1) e pelo handler `@auth.authenticate` (task langgraph-auth-1), todos
via `get_pool()`.
"""

from __future__ import annotations

from psycopg_pool import AsyncConnectionPool

_pool: AsyncConnectionPool | None = None


async def init_pool(conninfo: str) -> AsyncConnectionPool:
    """Abre o pool de conexões e o registra para reuso via `get_pool()`."""
    global _pool
    pool = AsyncConnectionPool(conninfo, open=False)
    await pool.open()
    _pool = pool
    return pool


async def close_pool() -> None:
    """Fecha o pool graciosamente, se houver um aberto."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def get_pool() -> AsyncConnectionPool:
    """Devolve o pool aberto por `init_pool` no startup do app."""
    if _pool is None:
        raise RuntimeError("Auth db pool not initialized; call init_pool() on startup first.")
    return _pool
