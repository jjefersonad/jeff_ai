"""Schema da tabela `token_usage_events` (metering de tokens).

Cria a tabela e índices em Postgres de forma idempotente, mesmo padrão de
`src/infrastructure/auth/schema.py` e `src/infrastructure/telegram/schema.py`.
"""

from __future__ import annotations

import psycopg

_CREATE_TOKEN_USAGE_EVENTS_TABLE = """
CREATE TABLE IF NOT EXISTS token_usage_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_key TEXT NOT NULL,
    thread_id TEXT,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    total_tokens INTEGER,
    source TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""

_CREATE_USER_KEY_CREATED_AT_INDEX = """
CREATE INDEX IF NOT EXISTS token_usage_events_user_key_created_at_idx
    ON token_usage_events (user_key, created_at DESC)
"""

_CREATE_USER_KEY_MODEL_INDEX = """
CREATE INDEX IF NOT EXISTS token_usage_events_user_key_model_idx
    ON token_usage_events (user_key, model)
"""


def ensure_schema(conninfo: str) -> None:
    """Cria a tabela `token_usage_events` e índices caso ainda não existam."""
    with psycopg.connect(conninfo, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(_CREATE_TOKEN_USAGE_EVENTS_TABLE)
            cur.execute(_CREATE_USER_KEY_CREATED_AT_INDEX)
            cur.execute(_CREATE_USER_KEY_MODEL_INDEX)
