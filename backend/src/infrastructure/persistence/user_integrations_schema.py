"""Schema Postgres da tabela `user_integrations`.

DDL idempotente via `psycopg` puro, mesmo padrão de
`src/infrastructure/auth/schema.py`. Uma única tabela para todo
`integration_type` (Telegram, e futuramente WhatsApp Business/SMTP) —
`config JSONB` guarda os dados de cada tipo, validados por schema Pydantic
na fronteira do use case, nunca via `CHECK` no banco (REQ-003 do spec
`user-integration-credentials-store`). Campos sensíveis dentro de `config`
são cifrados pela camada de repositório antes do insert; a coluna em si não
impõe formato para poder guardar ciphertext (REQ-002).
"""
from __future__ import annotations

import psycopg

_CREATE_USER_INTEGRATIONS_TABLE = """
CREATE TABLE IF NOT EXISTS user_integrations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    integration_type TEXT NOT NULL,
    config JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""

_CREATE_USER_ID_INDEX = """
CREATE INDEX IF NOT EXISTS user_integrations_user_id_idx ON user_integrations(user_id)
"""


def ensure_schema(conninfo: str) -> None:
    """Cria a tabela `user_integrations` e seus índices caso não existam (idempotente)."""
    with psycopg.connect(conninfo, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(_CREATE_USER_INTEGRATIONS_TABLE)
            cur.execute(_CREATE_USER_ID_INDEX)
