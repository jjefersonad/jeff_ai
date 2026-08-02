"""Schema do mapeamento chat_id -> thread_id do canal Telegram.

Cria a tabela `telegram_threads` em Postgres (idempotente), mesmo padrão de
`src/infrastructure/auth/schema.py`.
"""

from __future__ import annotations

import psycopg

_CREATE_TELEGRAM_THREADS_TABLE = """
CREATE TABLE IF NOT EXISTS telegram_threads (
    thread_id TEXT PRIMARY KEY,
    chat_id TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""

# `chat_id` was the original sole PK (one thread per chat). `telegram-slash-commands`
# needs multiple thread rows per `chat_id` (session history), so the PK moves to
# `thread_id` (already unique — a LangGraph UUID). This migrates any pre-existing
# table created under the old schema; on a fresh table it is a no-op.
_MIGRATE_CHAT_ID_PRIMARY_KEY_TO_THREAD_ID = """
DO $$
DECLARE
    old_pk_name TEXT;
BEGIN
    SELECT tc.constraint_name INTO old_pk_name
    FROM information_schema.table_constraints tc
    JOIN information_schema.key_column_usage kcu
      ON tc.constraint_name = kcu.constraint_name
     AND tc.table_schema = kcu.table_schema
    WHERE tc.table_name = 'telegram_threads'
      AND tc.constraint_type = 'PRIMARY KEY'
      AND kcu.column_name = 'chat_id';

    IF old_pk_name IS NOT NULL THEN
        EXECUTE format('ALTER TABLE telegram_threads DROP CONSTRAINT %I', old_pk_name);
        ALTER TABLE telegram_threads ADD PRIMARY KEY (thread_id);
    END IF;
END $$
"""

_CREATE_CHAT_ID_INDEX = """
CREATE INDEX IF NOT EXISTS telegram_threads_chat_id_idx ON telegram_threads(chat_id)
"""

_ADD_TITLE_COLUMN = """
ALTER TABLE telegram_threads ADD COLUMN IF NOT EXISTS title TEXT
"""

_ADD_ACTIVE_COLUMN = """
ALTER TABLE telegram_threads ADD COLUMN IF NOT EXISTS active BOOLEAN NOT NULL DEFAULT FALSE
"""

_CREATE_ONE_ACTIVE_PER_CHAT_INDEX = """
CREATE UNIQUE INDEX IF NOT EXISTS telegram_threads_one_active_per_chat
    ON telegram_threads(chat_id) WHERE active
"""


def ensure_telegram_threads_schema(conninfo: str) -> None:
    """Cria/atualiza a tabela `telegram_threads` de forma idempotente."""
    with psycopg.connect(conninfo, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(_CREATE_TELEGRAM_THREADS_TABLE)
            cur.execute(_MIGRATE_CHAT_ID_PRIMARY_KEY_TO_THREAD_ID)
            cur.execute(_CREATE_CHAT_ID_INDEX)
            cur.execute(_ADD_TITLE_COLUMN)
            cur.execute(_ADD_ACTIVE_COLUMN)
            cur.execute(_CREATE_ONE_ACTIVE_PER_CHAT_INDEX)
