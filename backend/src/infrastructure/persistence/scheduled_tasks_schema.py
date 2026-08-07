"""Schema Postgres da tabela `scheduled_tasks`.

DDL idempotente via `psycopg` puro, mesmo padrão de
`src/infrastructure/auth/schema.py`. Contém todo o contexto de negócio de
uma `ScheduledTask` (REQ-001 do spec `task-scheduling`) — o adapter do
scheduler (APScheduler) guarda apenas o gatilho (REQ-005), nunca estes
dados.

`owner_user_key` (REQ-008): dono da tarefa, mesma convenção `web:<user.id>` /
`telegram:<chat_id>` de `token_usage_events.user_key`
(`src/infrastructure/usage/schema.py`) — TEXT NOT NULL, sem FK, para cobrir
também o canal Telegram (allowlist single-user, sem linha em `users`).

`delivery_user_key` (scheduled-channel-routines): destino de notify/HITL
opcional; `NULL` = fallback para `owner_user_key`. Status `waiting_human`
cobre pausa HITL em runs agendados (Decision 4).
"""
from __future__ import annotations

import psycopg

_CREATE_SCHEDULED_TASKS_TABLE = """
CREATE TABLE IF NOT EXISTS scheduled_tasks (
    id TEXT PRIMARY KEY,
    prompt TEXT NOT NULL,
    thread_id TEXT NOT NULL,
    owner_user_key TEXT NOT NULL,
    delivery_user_key TEXT,
    skills TEXT[] NOT NULL DEFAULT '{}',
    tool_scope TEXT NOT NULL DEFAULT 'restricted'
        CHECK (tool_scope IN ('restricted', 'full')),
    schedule_kind TEXT NOT NULL CHECK (schedule_kind IN ('once', 'cron')),
    schedule_expr TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'scheduled'
        CHECK (status IN (
            'scheduled', 'running', 'succeeded', 'failed', 'waiting_human'
        )),
    timeout_seconds INTEGER NOT NULL DEFAULT 300,
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    last_run_at TIMESTAMPTZ,
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""

_CREATE_OWNER_USER_KEY_INDEX = """
CREATE INDEX IF NOT EXISTS scheduled_tasks_owner_user_key_idx
    ON scheduled_tasks (owner_user_key)
"""

_ADD_DELIVERY_USER_KEY_COLUMN = """
ALTER TABLE scheduled_tasks
    ADD COLUMN IF NOT EXISTS delivery_user_key TEXT
"""

# Bancos criados antes de scheduled-channel-routines têm CHECK de status sem
# `waiting_human`. CREATE TABLE IF NOT EXISTS não altera CHECK existente —
# drop + recreate nomeado, só quando a definição antiga ainda não inclui o
# valor (idempotente nos restarts seguintes).
_MIGRATE_STATUS_CHECK_WAITING_HUMAN = """
DO $$
DECLARE
    old_status_check TEXT;
BEGIN
    SELECT con.conname INTO old_status_check
    FROM pg_constraint con
    JOIN pg_class rel ON rel.oid = con.conrelid
    JOIN pg_namespace nsp ON nsp.oid = rel.relnamespace
    WHERE rel.relname = 'scheduled_tasks'
      AND nsp.nspname = current_schema()
      AND con.contype = 'c'
      AND pg_get_constraintdef(con.oid) LIKE '%status%'
      AND pg_get_constraintdef(con.oid) NOT LIKE '%waiting_human%';

    IF old_status_check IS NOT NULL THEN
        EXECUTE format(
            'ALTER TABLE scheduled_tasks DROP CONSTRAINT %I',
            old_status_check
        );
        ALTER TABLE scheduled_tasks
            ADD CONSTRAINT scheduled_tasks_status_check
            CHECK (status IN (
                'scheduled', 'running', 'succeeded', 'failed', 'waiting_human'
            ));
    END IF;
END $$
"""


def ensure_schema(conninfo: str) -> None:
    """Cria/atualiza a tabela `scheduled_tasks` de forma idempotente."""
    with psycopg.connect(conninfo, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(_CREATE_SCHEDULED_TASKS_TABLE)
            cur.execute(_ADD_DELIVERY_USER_KEY_COLUMN)
            cur.execute(_MIGRATE_STATUS_CHECK_WAITING_HUMAN)
            cur.execute(_CREATE_OWNER_USER_KEY_INDEX)
