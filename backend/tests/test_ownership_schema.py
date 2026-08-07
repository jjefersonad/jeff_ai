"""Teste de integração: `ownership.schema.ensure_schema` (task `user-data-isolation-task-db-1`).

Cobre os critérios de aceite da task:
- a tabela `generated_files` existe com o shape esperado (FK para `users`, CHECK de `kind`)
- `ensure_schema` é idempotente (rodar duas vezes não levanta erro)
- o índice único `(kind, filename)` de fato rejeita uma segunda inserção com o
  mesmo par — a asserção que faltava: os testes de `ownership/store.py` usam
  cursor fake e nunca exercitam a constraint real do Postgres.

Requer `INTEGRATION_POSTGRES_URI` apontando para um Postgres real — mesmo
padrão de `test_scheduled_task_repository.py`.
"""
from __future__ import annotations

import os
import uuid

import psycopg
import pytest
from psycopg.errors import UniqueViolation

from src.infrastructure.auth.schema import ensure_schema as ensure_auth_schema
from src.infrastructure.ownership.schema import ensure_schema

INTEGRATION_URI_ENV = "INTEGRATION_POSTGRES_URI"
pytestmark = pytest.mark.skipif(
    not os.environ.get(INTEGRATION_URI_ENV),
    reason=(
        f"Requer Postgres de teste real. Defina {INTEGRATION_URI_ENV} "
        "(ex.: postgresql://jeff_ia:jeff_ia@localhost:5436/jeff_ia) "
        "para rodar este teste."
    ),
)


def _uri() -> str:
    return os.environ[INTEGRATION_URI_ENV]


@pytest.fixture(autouse=True)
def _ensure_tables() -> None:
    # `generated_files.user_id` referencia `users(id)` — precisa existir primeiro.
    ensure_auth_schema(_uri())
    ensure_schema(_uri())


@pytest.fixture
def user_id() -> str:
    """Usuário descartável só para satisfazer a FK de `generated_files.user_id`."""
    with psycopg.connect(_uri(), autocommit=True) as conn, conn.cursor() as cur:
        username = f"test-ownership-schema-{uuid.uuid4()}"
        cur.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (%s, 'x', 'user') RETURNING id",
            (username,),
        )
        row = cur.fetchone()
        assert row is not None
        new_id = str(row[0])
        yield new_id
        cur.execute("DELETE FROM generated_files WHERE user_id = %s", (new_id,))
        cur.execute("DELETE FROM users WHERE id = %s", (new_id,))


def test_ensure_schema_is_idempotent() -> None:
    ensure_schema(_uri())  # segunda chamada (a primeira já rodou no fixture) não levanta.


def test_generated_files_accepts_a_valid_row(user_id: str) -> None:
    filename = f"report-{uuid.uuid4()}.docx"
    with psycopg.connect(_uri(), autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO generated_files (user_id, kind, filename) VALUES (%s, %s, %s)",
            (user_id, "docx", filename),
        )
        cur.execute(
            "SELECT user_id, kind FROM generated_files WHERE filename = %s", (filename,)
        )
        row = cur.fetchone()
    assert row == (uuid.UUID(user_id), "docx")


def test_generated_files_accepts_pdf_kind(user_id: str) -> None:
    """REQ-ADD-010 / unit-1: insert com kind=pdf deve ser aceito após ensure_schema."""
    filename = f"report-{uuid.uuid4()}.pdf"
    with psycopg.connect(_uri(), autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO generated_files (user_id, kind, filename) VALUES (%s, %s, %s)",
            (user_id, "pdf", filename),
        )
        cur.execute(
            "SELECT user_id, kind FROM generated_files WHERE filename = %s", (filename,)
        )
        row = cur.fetchone()
    assert row == (uuid.UUID(user_id), "pdf")


def test_generated_files_accepts_html_kind(user_id: str) -> None:
    """REQ-ADD-012 / schema-html unit-1: insert kind=html após ensure_schema."""
    filename = f"preview-{uuid.uuid4()}.html"
    with psycopg.connect(_uri(), autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO generated_files (user_id, kind, filename) VALUES (%s, %s, %s)",
            (user_id, "html", filename),
        )
        cur.execute(
            "SELECT user_id, kind FROM generated_files WHERE filename = %s", (filename,)
        )
        row = cur.fetchone()
    assert row == (uuid.UUID(user_id), "html")


def test_ensure_schema_migrates_legacy_kind_check_without_pdf(user_id: str) -> None:
    """REQ-ADD-010 / unit-2: CHECK legado sem pdf é migrado por ensure_schema."""
    # Restaura a constraint pré-html-document-tools (sem pdf), depois migra.
    with psycopg.connect(_uri(), autocommit=True) as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM generated_files WHERE kind = 'pdf'")
        cur.execute(
            """
            ALTER TABLE generated_files
                DROP CONSTRAINT IF EXISTS generated_files_kind_check
            """
        )
        cur.execute(
            """
            ALTER TABLE generated_files
                ADD CONSTRAINT generated_files_kind_check
                CHECK (kind IN ('docx', 'xlsx', 'pptx', 'image', 'reference'))
            """
        )

    filename_blocked = f"blocked-{uuid.uuid4()}.pdf"
    with psycopg.connect(_uri(), autocommit=True) as conn:
        with pytest.raises(psycopg.errors.CheckViolation):
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO generated_files (user_id, kind, filename) "
                    "VALUES (%s, %s, %s)",
                    (user_id, "pdf", filename_blocked),
                )

    ensure_schema(_uri())
    ensure_schema(_uri())  # idempotente

    filename = f"migrated-{uuid.uuid4()}.pdf"
    with psycopg.connect(_uri(), autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO generated_files (user_id, kind, filename) VALUES (%s, %s, %s)",
            (user_id, "pdf", filename),
        )
        cur.execute(
            "SELECT kind FROM generated_files WHERE filename = %s", (filename,)
        )
        row = cur.fetchone()
    assert row == ("pdf",)


def test_ensure_schema_migrates_kind_check_without_html(user_id: str) -> None:
    """REQ-ADD-012 / schema-html unit-2: CHECK com pdf mas sem html é migrado."""
    with psycopg.connect(_uri(), autocommit=True) as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM generated_files WHERE kind = 'html'")
        cur.execute(
            """
            ALTER TABLE generated_files
                DROP CONSTRAINT IF EXISTS generated_files_kind_check
            """
        )
        cur.execute(
            """
            ALTER TABLE generated_files
                ADD CONSTRAINT generated_files_kind_check
                CHECK (kind IN (
                    'docx', 'xlsx', 'pptx', 'pdf', 'image', 'reference'
                ))
            """
        )

    filename_blocked = f"blocked-{uuid.uuid4()}.html"
    with psycopg.connect(_uri(), autocommit=True) as conn:
        with pytest.raises(psycopg.errors.CheckViolation):
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO generated_files (user_id, kind, filename) "
                    "VALUES (%s, %s, %s)",
                    (user_id, "html", filename_blocked),
                )

    ensure_schema(_uri())
    ensure_schema(_uri())  # idempotente

    filename = f"migrated-{uuid.uuid4()}.html"
    with psycopg.connect(_uri(), autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO generated_files (user_id, kind, filename) VALUES (%s, %s, %s)",
            (user_id, "html", filename),
        )
        cur.execute(
            "SELECT kind FROM generated_files WHERE filename = %s", (filename,)
        )
        row = cur.fetchone()
    assert row == ("html",)


def test_generated_files_rejects_invalid_kind(user_id: str) -> None:
    with psycopg.connect(_uri(), autocommit=True) as conn:
        with pytest.raises(psycopg.errors.CheckViolation):
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO generated_files (user_id, kind, filename) VALUES (%s, %s, %s)",
                    (user_id, "not-a-real-kind", "x.docx"),
                )


def test_unique_kind_filename_rejects_duplicate_insert(user_id: str) -> None:
    """Critério de aceite explícito de `task-db-1`: índice único em
    `(kind, filename)` confirmado via teste de inserção duplicada (deve falhar)."""
    filename = f"dup-{uuid.uuid4()}.docx"
    with psycopg.connect(_uri(), autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO generated_files (user_id, kind, filename) VALUES (%s, %s, %s)",
            (user_id, "docx", filename),
        )

    with psycopg.connect(_uri(), autocommit=True) as conn:
        with pytest.raises(UniqueViolation):
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO generated_files (user_id, kind, filename) VALUES (%s, %s, %s)",
                    (user_id, "docx", filename),
                )


def test_unique_constraint_is_scoped_to_kind_and_filename_pair(user_id: str) -> None:
    """Mesmo `filename`, `kind` diferente — não deve colidir (a constraint é no par)."""
    filename = f"same-name-{uuid.uuid4()}"
    with psycopg.connect(_uri(), autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO generated_files (user_id, kind, filename) VALUES (%s, %s, %s)",
            (user_id, "docx", filename),
        )
        cur.execute(
            "INSERT INTO generated_files (user_id, kind, filename) VALUES (%s, %s, %s)",
            (user_id, "image", filename),
        )
        cur.execute(
            "SELECT count(*) FROM generated_files WHERE filename = %s", (filename,)
        )
        row = cur.fetchone()
    assert row == (2,)
