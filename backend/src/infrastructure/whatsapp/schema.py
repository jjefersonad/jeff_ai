"""Schema do mapeamento phone_number -> thread_id do canal WhatsApp.

Cria a tabela `whatsapp_threads` em Postgres (idempotente), mesmo padrão de
`src/infrastructure/telegram/schema.py` — simplificado para um único
`thread_id` por `phone_number` (sem múltiplas sessões/`active`/`title`, que
telegram-slash-commands adicionou ao Telegram; fora de escopo deste change,
ver `whatsapp-evolution-channel-design`).
"""

from __future__ import annotations

import psycopg

_CREATE_WHATSAPP_THREADS_TABLE = """
CREATE TABLE IF NOT EXISTS whatsapp_threads (
    phone_number TEXT PRIMARY KEY,
    thread_id TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""


def ensure_whatsapp_threads_schema(conninfo: str) -> None:
    """Cria a tabela `whatsapp_threads` caso não exista (idempotente)."""
    with psycopg.connect(conninfo, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(_CREATE_WHATSAPP_THREADS_TABLE)
