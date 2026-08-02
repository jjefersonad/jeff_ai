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
"""
from __future__ import annotations

import psycopg

_CREATE_SCHEDULED_TASKS_TABLE = """
CREATE TABLE IF NOT EXISTS scheduled_tasks (
    id TEXT PRIMARY KEY,
    prompt TEXT NOT NULL,
    thread_id TEXT NOT NULL,
    owner_user_key TEXT NOT NULL,
    skills TEXT[] NOT NULL DEFAULT '{}',
    tool_scope TEXT NOT NULL DEFAULT 'restricted'
        CHECK (tool_scope IN ('restricted', 'full')),
    schedule_kind TEXT NOT NULL CHECK (schedule_kind IN ('once', 'cron')),
    schedule_expr TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'scheduled'
        CHECK (status IN ('scheduled', 'running', 'succeeded', 'failed')),
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


def ensure_schema(conninfo: str) -> None:
    """Cria a tabela `scheduled_tasks` e seus índices caso não existam (idempotente)."""
    with psycopg.connect(conninfo, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(_CREATE_SCHEDULED_TASKS_TABLE)
            cur.execute(_CREATE_OWNER_USER_KEY_INDEX)
