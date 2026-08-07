"""Schema do mapeamento phone_number -> thread_id do canal WhatsApp.

Cria a tabela `whatsapp_threads` em Postgres (idempotente). Desde
`whatsapp-slash-commands`, suporta múltiplas threads por `phone_number` (uma
"ativa" por vez) — mesmo padrão de `src/infrastructure/telegram/schema.py`,
adaptado: `phone_number` deixa de ser a PRIMARY KEY (`thread_id`, já único,
assume esse papel), ganhando `title`/`active` e um índice único parcial.

Diferente do Telegram, linhas migradas do formato antigo (uma única linha por
`phone_number`) são marcadas `active=TRUE` imediatamente na própria migração
— não há ambiguidade sobre qual thread deveria ficar ativa (só existia uma),
e deixar `active=FALSE` faria a conversa em andamento "sumir" da resolução de
`get_or_create_thread_id` até o usuário mandar um comando.
"""

from __future__ import annotations

import psycopg

_CREATE_WHATSAPP_THREADS_TABLE = """
CREATE TABLE IF NOT EXISTS whatsapp_threads (
    thread_id TEXT PRIMARY KEY,
    phone_number TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""

# `phone_number` era o PK original (uma thread por número). `whatsapp-slash-
# commands` precisa de múltiplas linhas por `phone_number` (histórico de
# sessões), então a PK move para `thread_id` (já único — UUID do LangGraph).
# Migra qualquer tabela pré-existente que ainda tenha `phone_number` como PK;
# num fresh install é no-op. A ativação das linhas migradas acontece aqui
# dentro (não como UPDATE solto) porque só deve rodar uma vez, exatamente no
# instante da transição de formato — depois que `phone_number` deixa de ser
# PK, `old_pk_name` nunca mais é encontrado, então este bloco nunca roda de
# novo (senão reativaria threads legitimamente inativas em todo restart).
_MIGRATE_PHONE_NUMBER_PRIMARY_KEY_TO_THREAD_ID = """
DO $$
DECLARE
    old_pk_name TEXT;
BEGIN
    SELECT tc.constraint_name INTO old_pk_name
    FROM information_schema.table_constraints tc
    JOIN information_schema.key_column_usage kcu
      ON tc.constraint_name = kcu.constraint_name
     AND tc.table_schema = kcu.table_schema
    WHERE tc.table_name = 'whatsapp_threads'
      AND tc.constraint_type = 'PRIMARY KEY'
      AND kcu.column_name = 'phone_number';

    IF old_pk_name IS NOT NULL THEN
        EXECUTE format('ALTER TABLE whatsapp_threads DROP CONSTRAINT %I', old_pk_name);
        ALTER TABLE whatsapp_threads ADD PRIMARY KEY (thread_id);
        UPDATE whatsapp_threads SET active = TRUE;
    END IF;
END $$
"""

_CREATE_PHONE_NUMBER_INDEX = """
CREATE INDEX IF NOT EXISTS whatsapp_threads_phone_number_idx ON whatsapp_threads(phone_number)
"""

_ADD_TITLE_COLUMN = """
ALTER TABLE whatsapp_threads ADD COLUMN IF NOT EXISTS title TEXT
"""

_ADD_ACTIVE_COLUMN = """
ALTER TABLE whatsapp_threads ADD COLUMN IF NOT EXISTS active BOOLEAN NOT NULL DEFAULT FALSE
"""

_CREATE_ONE_ACTIVE_PER_NUMBER_INDEX = """
CREATE UNIQUE INDEX IF NOT EXISTS whatsapp_threads_one_active_per_number
    ON whatsapp_threads(phone_number) WHERE active
"""


def ensure_whatsapp_threads_schema(conninfo: str) -> None:
    """Cria/atualiza a tabela `whatsapp_threads` de forma idempotente."""
    with psycopg.connect(conninfo, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(_CREATE_WHATSAPP_THREADS_TABLE)
            cur.execute(_ADD_TITLE_COLUMN)
            cur.execute(_ADD_ACTIVE_COLUMN)
            cur.execute(_MIGRATE_PHONE_NUMBER_PRIMARY_KEY_TO_THREAD_ID)
            cur.execute(_CREATE_PHONE_NUMBER_INDEX)
            cur.execute(_CREATE_ONE_ACTIVE_PER_NUMBER_INDEX)
