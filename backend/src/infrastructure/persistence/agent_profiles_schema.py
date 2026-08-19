"""Schema SQL de `agent_profiles`.

`ensure_agent_profiles_schema(conninfo)` é idempotente (CREATE TABLE/INDEX
IF NOT EXISTS). Chamado no bootstrap do backend junto dos outros schemas
(mesmo padrão de `ensure_email_schema`).
"""
from __future__ import annotations

import psycopg

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS agent_profiles (
    id UUID PRIMARY KEY,
    user_id TEXT NOT NULL,
    name TEXT NOT NULL,
    slug TEXT NOT NULL,
    system_prompt TEXT NOT NULL,
    skills_allowlist JSONB,
    tools_allowlist JSONB,
    mcp_allowlist JSONB,
    tier SMALLINT NOT NULL DEFAULT 1 CHECK (tier BETWEEN 1 AND 4),
    model_override TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    archived_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
"""


CREATE_INDEX_USER_SLUG_ACTIVE_UNIQ_SQL = """
CREATE UNIQUE INDEX IF NOT EXISTS agent_profiles_user_slug_active_uniq
    ON agent_profiles (user_id, slug)
    WHERE archived_at IS NULL
"""


CREATE_INDEX_USER_ACTIVE_SQL = """
CREATE INDEX IF NOT EXISTS agent_profiles_user_active_idx
    ON agent_profiles (user_id)
    WHERE is_active = TRUE
"""


ADD_MCP_ALLOWLIST_COLUMN_SQL = """
ALTER TABLE agent_profiles ADD COLUMN IF NOT EXISTS mcp_allowlist JSONB
"""


def ensure_agent_profiles_schema(conninfo: str) -> None:
    """Cria a tabela `agent_profiles` e seus índices (idempotente)."""
    with psycopg.connect(conninfo) as conn:
        with conn.cursor() as cur:
            cur.execute(CREATE_TABLE_SQL)
            cur.execute(ADD_MCP_ALLOWLIST_COLUMN_SQL)
            cur.execute(CREATE_INDEX_USER_SLUG_ACTIVE_UNIQ_SQL)
            cur.execute(CREATE_INDEX_USER_ACTIVE_SQL)
        conn.commit()


ensure_schema = ensure_agent_profiles_schema
