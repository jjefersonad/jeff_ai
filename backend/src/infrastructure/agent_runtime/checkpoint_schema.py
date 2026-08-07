"""DDL aditivo idempotente para o schema de checkpoint do LangGraph.

As tabelas `checkpoint_*` são owned by LangGraph (schema UUID criado pelo
runtime API). Este módulo NÃO chama `AsyncPostgresSaver.setup()` nem executa
as `CREATE TABLE` TEXT das `MIGRATIONS` iniciais da lib — só aplica ALTERs
aditivos seguros (ex.: `task_path`) no boot do processo.
"""

from __future__ import annotations

import psycopg

# Alinhado a `langgraph.checkpoint.postgres.base.MIGRATIONS` (entrada aditiva
# de `task_path`). Não inclui CREATE TABLE / INDEX CONCURRENTLY.
_ADD_TASK_PATH_COLUMN = (
    "ALTER TABLE checkpoint_writes "
    "ADD COLUMN IF NOT EXISTS task_path TEXT NOT NULL DEFAULT ''"
)


def ensure_langgraph_checkpoint_schema(conninfo: str) -> None:
    """Garante migrations aditivas do checkpointer no boot (idempotente).

    MUST NOT recriar tabelas com tipos TEXT quando o schema legado já usa UUID.
    """
    with psycopg.connect(conninfo, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(_ADD_TASK_PATH_COLUMN)
