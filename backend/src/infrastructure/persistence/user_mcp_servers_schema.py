"""Schema Postgres da tabela `user_mcp_servers`.

DDL idempotente via `psycopg` puro, mesmo padrão de
`user_integrations_schema.py`. Uma linha por `(user_id, name)` — dois
usuários podem declarar servidores com o mesmo nome sem colisão (REQ-001 do
spec `user-mcp-server-store`). `args`/`env`/`headers` guardam JSON; valores
sensíveis dentro de `env`/`headers` são cifrados pela camada de repositório
antes do insert (REQ-002) — a coluna em si não impõe formato para poder
guardar ciphertext.
"""
from __future__ import annotations

import psycopg

_CREATE_USER_MCP_SERVERS_TABLE = """
CREATE TABLE IF NOT EXISTS user_mcp_servers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    name TEXT NOT NULL,
    transport TEXT NOT NULL,
    command TEXT,
    args JSONB,
    url TEXT,
    env JSONB,
    headers JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, name)
)
"""

_CREATE_USER_ID_INDEX = """
CREATE INDEX IF NOT EXISTS user_mcp_servers_user_id_idx ON user_mcp_servers(user_id)
"""


def ensure_schema(conninfo: str) -> None:
    """Cria a tabela `user_mcp_servers` e seus índices caso não existam (idempotente)."""
    with psycopg.connect(conninfo, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(_CREATE_USER_MCP_SERVERS_TABLE)
            cur.execute(_CREATE_USER_ID_INDEX)
