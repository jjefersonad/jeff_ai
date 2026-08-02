"""Schema de `chat_attachments`: arquivos anexados a uma mensagem de chat pelo usuário.

Cria a tabela `chat_attachments` em Postgres (idempotente), associando cada
arquivo enviado ao `thread_id` da conversa e ao `user_id` de quem o enviou.
Depende da tabela `users` já existir (FK) — chamar `ensure_schema` depois de
`src.infrastructure.auth.schema.ensure_schema`, seguindo o mesmo padrão de
`src.infrastructure.ownership.schema`. `thread_id` não tem FK: threads são
geridas pelo checkpointer do LangGraph, fora do schema desta aplicação.
"""

from __future__ import annotations

import psycopg

_CREATE_CHAT_ATTACHMENTS_TABLE = """
CREATE TABLE IF NOT EXISTS chat_attachments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    thread_id TEXT NOT NULL,
    user_id UUID NOT NULL REFERENCES users(id),
    filename TEXT NOT NULL,
    content_type TEXT NOT NULL,
    size_bytes BIGINT NOT NULL,
    storage_path TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""

_CREATE_CHAT_ATTACHMENTS_THREAD_INDEX = """
CREATE INDEX IF NOT EXISTS idx_chat_attachments_thread_id
    ON chat_attachments (thread_id)
"""


def ensure_schema(conninfo: str) -> None:
    """Cria a tabela `chat_attachments` (e seu índice por thread) caso ainda não existam."""
    with psycopg.connect(conninfo, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(_CREATE_CHAT_ATTACHMENTS_TABLE)
            cur.execute(_CREATE_CHAT_ATTACHMENTS_THREAD_INDEX)
