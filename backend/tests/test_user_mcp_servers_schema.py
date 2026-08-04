"""Teste de integração: `user_mcp_servers_schema.ensure_schema` (task
`user-scoped-mcp-config-storage-task-db-1`).

Cobre REQ-001 do spec `user-mcp-server-store`:
- DDL idempotente da tabela `user_mcp_servers` (rodar duas vezes não levanta)
- índice único `(user_id, name)` rejeita duplicata para o mesmo usuário, mas
  permite o mesmo `name` para usuários distintos (chave é o par, não `name`
  isolado)

Requer `INTEGRATION_POSTGRES_URI` apontando para um Postgres real — mesmo
padrão de `test_ownership_schema.py`.
"""
from __future__ import annotations

import os
import uuid

import psycopg
import pytest
from psycopg.errors import UniqueViolation

from src.infrastructure.auth.schema import ensure_schema as ensure_auth_schema
from src.infrastructure.persistence.user_mcp_servers_schema import ensure_schema

INTEGRATION_URI_ENV = "INTEGRATION_POSTGRES_URI"
pytestmark = pytest.mark.skipif(
    not os.environ.get(INTEGRATION_URI_ENV),
    reason=(
        f"Requer Postgres de teste real. Defina {INTEGRATION_URI_ENV} "
        "(ex.: postgresql://jeff_ia:jeff_ia@localhost:5436/jeff_ia) "
        "para rodar este teste."
    ),
)


def _uri() -> str:
    return os.environ[INTEGRATION_URI_ENV]


@pytest.fixture(autouse=True)
def _ensure_tables() -> None:
    # `user_mcp_servers.user_id` referencia `users(id)` — precisa existir primeiro.
    ensure_auth_schema(_uri())
    ensure_schema(_uri())


@pytest.fixture
def make_user():
    created_ids: list[str] = []

    def _make(label: str) -> str:
        with psycopg.connect(_uri(), autocommit=True) as conn, conn.cursor() as cur:
            username = f"test-user-mcp-servers-{label}-{uuid.uuid4()}"
            cur.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (%s, 'x', 'user') RETURNING id",
                (username,),
            )
            row = cur.fetchone()
            assert row is not None
            new_id = str(row[0])
        created_ids.append(new_id)
        return new_id

    yield _make

    with psycopg.connect(_uri(), autocommit=True) as conn, conn.cursor() as cur:
        for user_id in created_ids:
            cur.execute("DELETE FROM user_mcp_servers WHERE user_id = %s", (user_id,))
            cur.execute("DELETE FROM users WHERE id = %s", (user_id,))


def test_ensure_schema_is_idempotent() -> None:
    ensure_schema(_uri())  # segunda chamada (a primeira já rodou no fixture) não levanta.


def test_unique_user_id_name_rejects_duplicate_insert(make_user) -> None:
    user_id = make_user("dup")
    with psycopg.connect(_uri(), autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO user_mcp_servers (user_id, name, transport, command) "
            "VALUES (%s, %s, 'stdio', 'npx')",
            (user_id, "zernio"),
        )

    with psycopg.connect(_uri(), autocommit=True) as conn:
        with pytest.raises(UniqueViolation):
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO user_mcp_servers (user_id, name, transport, command) "
                    "VALUES (%s, %s, 'stdio', 'npx')",
                    (user_id, "zernio"),
                )


def test_unique_constraint_is_scoped_to_user_id_and_name_pair(make_user) -> None:
    user_a = make_user("a")
    user_b = make_user("b")
    with psycopg.connect(_uri(), autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO user_mcp_servers (user_id, name, transport, command) "
            "VALUES (%s, %s, 'stdio', 'npx')",
            (user_a, "zernio"),
        )
        cur.execute(
            "INSERT INTO user_mcp_servers (user_id, name, transport, command) "
            "VALUES (%s, %s, 'stdio', 'npx')",
            (user_b, "zernio"),
        )
        cur.execute("SELECT count(*) FROM user_mcp_servers WHERE name = %s", ("zernio",))
        row = cur.fetchone()
    assert row == (2,)
