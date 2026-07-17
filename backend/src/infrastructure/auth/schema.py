"""Schema de autenticação e bootstrap do primeiro usuário admin.

Cria as tabelas `users` e `sessions` em Postgres (idempotente) e garante, no
startup, que exista pelo menos um usuário `admin` — lido de
`ADMIN_USERNAME`/`ADMIN_PASSWORD_HASH`. Usa uma conexão avulsa: o pool
compartilhado (`src/infrastructure/auth/db.py`) é responsabilidade da tarefa
seguinte (`task-auth-core-1`), que depende deste schema já existir.
"""

from __future__ import annotations

import os

import psycopg

_CREATE_USERS_TABLE = """
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('admin', 'user')),
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""

_CREATE_SESSIONS_TABLE = """
CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL
)
"""


class AuthBootstrapError(RuntimeError):
    """Configuração ausente ou inválida para o bootstrap de autenticação."""


def ensure_schema(conninfo: str) -> None:
    """Cria as tabelas `users`/`sessions` caso ainda não existam."""
    with psycopg.connect(conninfo, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(_CREATE_USERS_TABLE)
            cur.execute(_CREATE_SESSIONS_TABLE)


def bootstrap_admin(conninfo: str) -> None:
    """Cria o primeiro usuário admin se a tabela `users` estiver vazia.

    Lê `ADMIN_USERNAME`/`ADMIN_PASSWORD_HASH` do ambiente (o segundo já
    esperado como hash bcrypt, nunca senha em texto plano). Se a tabela já
    tem usuários, não faz nada. Se está vazia e as envs faltam, levanta
    `AuthBootstrapError` para interromper o startup (cenário "Inicialização
    sem credenciais de admin").
    """
    with psycopg.connect(conninfo, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM users")
            row = cur.fetchone()
            count = row[0] if row else 0
            if count > 0:
                return

            username = os.environ.get("ADMIN_USERNAME")
            password_hash = os.environ.get("ADMIN_PASSWORD_HASH")
            if not username or not password_hash:
                raise AuthBootstrapError(
                    "ADMIN_USERNAME e ADMIN_PASSWORD_HASH sao obrigatorias para "
                    "o bootstrap do primeiro usuario admin (tabela 'users' vazia)."
                )

            cur.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (%s, %s, 'admin')",
                (username, password_hash),
            )


def init_auth_schema(conninfo: str) -> None:
    """Garante o schema de autenticação e o bootstrap do admin inicial."""
    ensure_schema(conninfo)
    bootstrap_admin(conninfo)
