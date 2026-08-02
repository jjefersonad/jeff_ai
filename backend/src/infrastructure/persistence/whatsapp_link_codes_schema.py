"""Schema Postgres da tabela `whatsapp_link_codes`.

DDL idempotente via `psycopg` puro, mesmo padrão de
`src/infrastructure/persistence/telegram_link_codes_schema.py`. Mantida
separada de `user_integrations` para que códigos expirados/consumidos nunca
poluam a tabela de credenciais (mesmo raciocínio da design Decision 3 de
`user-integration-credentials`, aplicado ao WhatsApp em `whatsapp-evolution-
channel-design`). Cada código é single-use, com TTL curto controlado em
`expires_at` (whatsapp-channel REQ-001).
"""
from __future__ import annotations

import psycopg

_CREATE_WHATSAPP_LINK_CODES_TABLE = """
CREATE TABLE IF NOT EXISTS whatsapp_link_codes (
    code TEXT PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id),
    expires_at TIMESTAMPTZ NOT NULL
)
"""


def ensure_schema(conninfo: str) -> None:
    """Cria a tabela `whatsapp_link_codes` caso não exista (idempotente)."""
    with psycopg.connect(conninfo, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(_CREATE_WHATSAPP_LINK_CODES_TABLE)
