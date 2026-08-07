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

_KIND_CHECK = (
    "kind IN ('docx', 'xlsx', 'pptx', 'pdf', 'html', 'image', 'reference')"
)

_CREATE_GENERATED_FILES_TABLE = f"""
CREATE TABLE IF NOT EXISTS generated_files (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    kind TEXT NOT NULL CHECK ({_KIND_CHECK}),
    filename TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (kind, filename)
)
"""

# Bancos criados antes de html-document-tools (ou só com pdf) têm CHECK
# incompleto. CREATE TABLE IF NOT EXISTS não altera CHECK existente —
# drop + recreate nomeado quando falta `pdf` ou `html` (idempotente).
_MIGRATE_KIND_CHECK = """
DO $$
DECLARE
    old_kind_check TEXT;
BEGIN
    SELECT con.conname INTO old_kind_check
    FROM pg_constraint con
    JOIN pg_class rel ON rel.oid = con.conrelid
    JOIN pg_namespace nsp ON nsp.oid = rel.relnamespace
    WHERE rel.relname = 'generated_files'
      AND nsp.nspname = current_schema()
      AND con.contype = 'c'
      AND pg_get_constraintdef(con.oid) LIKE '%kind%'
      AND (
          pg_get_constraintdef(con.oid) NOT LIKE '%pdf%'
          OR pg_get_constraintdef(con.oid) NOT LIKE '%html%'
      );

    IF old_kind_check IS NOT NULL THEN
        EXECUTE format(
            'ALTER TABLE generated_files DROP CONSTRAINT %I',
            old_kind_check
        );
        ALTER TABLE generated_files
            ADD CONSTRAINT generated_files_kind_check
            CHECK (kind IN (
                'docx', 'xlsx', 'pptx', 'pdf', 'html', 'image', 'reference'
            ));
    END IF;
END $$
"""


def ensure_schema(conninfo: str) -> None:
    """Cria/atualiza a tabela `generated_files` de forma idempotente."""
    with psycopg.connect(conninfo, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(_CREATE_GENERATED_FILES_TABLE)
            cur.execute(_MIGRATE_KIND_CHECK)
