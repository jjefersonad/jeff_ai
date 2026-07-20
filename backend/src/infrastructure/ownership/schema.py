"""Schema de `generated_files`: rastreio de dono para documentos e imagens gerados.

Cria a tabela `generated_files` em Postgres (idempotente), associando cada
arquivo gerado (`kind` + `filename`) ao `user_id` de quem o gerou. Depende da
tabela `users` já existir (FK) — chamar `ensure_schema` depois de
`src.infrastructure.auth.schema.ensure_schema`. Usa uma conexão avulsa,
seguindo o mesmo padrão de `auth/schema.py`: o pool compartilhado
(`src/infrastructure/auth/db.py`) é usado pela aplicação, não pelo bootstrap.
"""

from __future__ import annotations

import psycopg

_CREATE_GENERATED_FILES_TABLE = """
CREATE TABLE IF NOT EXISTS generated_files (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    kind TEXT NOT NULL CHECK (kind IN ('docx', 'xlsx', 'pptx', 'image', 'reference')),
    filename TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (kind, filename)
)
"""


def ensure_schema(conninfo: str) -> None:
    """Cria a tabela `generated_files` caso ainda não exista."""
    with psycopg.connect(conninfo, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(_CREATE_GENERATED_FILES_TABLE)
