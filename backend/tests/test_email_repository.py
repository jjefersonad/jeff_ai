"""Testes de `PostgresEmailRepository.upsert_email` (email-client-imap-mvp-task-sync-2).

Unit-1 (REQ-005 email-account-management): upsert é idempotente por
`email_account_id`+`message_id` (não duplica linha em `emails`), e persiste
exatamente uma linha em `email_attachments` por anexo, vinculada via
`email_id`.

Requer `INTEGRATION_POSTGRES_URI` (ou use o mesmo Postgres de dev) — mesmo
padrão de `tests/test_crm_repository.py`.
"""
from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime

import psycopg
import pytest

from src.domain.email.models import ParsedAttachment, ParsedMessage
from src.infrastructure.auth.schema import ensure_schema as ensure_auth_schema
from src.infrastructure.persistence.crm_schema import ensure_crm_schema
from src.infrastructure.persistence.email_schema import ensure_email_schema
from src.infrastructure.persistence.user_integrations_schema import (
    ensure_schema as ensure_user_integrations_schema,
)

INTEGRATION_URI_ENV = "INTEGRATION_POSTGRES_URI"
pytestmark = pytest.mark.skipif(
    not os.environ.get(INTEGRATION_URI_ENV),
    reason=(
        f"Requer Postgres de teste real. Defina {INTEGRATION_URI_ENV} "
        "(ex.: postgresql://jeff_ia:jeff_ia@localhost:5436/jeff_ia)."
    ),
)


def _uri() -> str:
    return os.environ[INTEGRATION_URI_ENV]


@pytest.fixture(autouse=True)
def _setup_postgres() -> None:
    ensure_auth_schema(_uri())
    ensure_crm_schema(_uri())
    ensure_user_integrations_schema(_uri())
    ensure_email_schema(_uri())
    with psycopg.connect(_uri()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "TRUNCATE TABLE email_attachments, emails, email_accounts, "
                "user_integrations, crm_contacts CASCADE"
            )
        conn.commit()


def _insert_test_user() -> str:
    user_id = str(uuid.uuid4())
    with psycopg.connect(_uri()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO users (id, username, password_hash) "
                "VALUES (%s, %s, %s) ON CONFLICT (id) DO NOTHING",
                (user_id, f"email-test-{user_id}", "x"),
            )
        conn.commit()
    return user_id


def _insert_email_account(user_id: str) -> str:
    """Cria `user_integrations` + `email_accounts` direto via SQL (setup, não SUT)."""
    integration_id = str(uuid.uuid4())
    account_id = str(uuid.uuid4())
    with psycopg.connect(_uri()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO user_integrations (id, user_id, integration_type, config) "
                "VALUES (%s, %s, 'imap', '{}'::jsonb)",
                (integration_id, user_id),
            )
            cur.execute(
                "INSERT INTO email_accounts "
                "(id, user_id, user_integration_id, display_name) "
                "VALUES (%s, %s, %s, 'Test Account')",
                (account_id, user_id, integration_id),
            )
        conn.commit()
    return account_id


def _parsed_message(**overrides: object) -> ParsedMessage:
    kwargs: dict[str, object] = {
        "uid": "101",
        "message_id": "msg-101@example.com",
        "folder": "INBOX",
        "from_address": "alice@example.com",
        "from_name": "Alice",
        "to_addresses": ["bob@example.com"],
        "subject": "Hello",
        "body_html": "<p>Hi</p>",
        "body_text": "Hi",
        "received_at": datetime.now(UTC),
    }
    kwargs.update(overrides)
    return ParsedMessage(**kwargs)  # type: ignore[arg-type]


async def test_upsert_email_is_idempotent_on_account_and_message_id() -> None:
    from src.infrastructure.persistence.email_repository import (
        PostgresEmailRepository,
    )

    user_id = _insert_test_user()
    account_id = _insert_email_account(user_id)
    repo = PostgresEmailRepository(_uri())
    message = _parsed_message()

    first = await repo.upsert_email(account_id, message)
    second = await repo.upsert_email(account_id, message)

    assert first.id == second.id
    stored = await repo.list_by_account(user_id, account_id, "INBOX", limit=10, offset=0)
    assert len(stored) == 1
    assert stored[0].message_id == "msg-101@example.com"


async def test_upsert_email_persists_one_attachment_row_per_attachment() -> None:
    from src.infrastructure.persistence.email_repository import (
        PostgresEmailRepository,
    )

    user_id = _insert_test_user()
    account_id = _insert_email_account(user_id)
    repo = PostgresEmailRepository(_uri())
    message = _parsed_message(message_id="msg-with-attachments@example.com")
    attachments = [
        ParsedAttachment(
            filename="invoice.pdf",
            mime_type="application/pdf",
            size_bytes=1234,
            storage_path="/data/email_attachments/invoice.pdf",
        ),
        ParsedAttachment(
            filename="photo.png",
            mime_type="image/png",
            size_bytes=5678,
            storage_path="/data/email_attachments/photo.png",
        ),
    ]

    saved = await repo.upsert_email(account_id, message, attachments)

    with psycopg.connect(_uri()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT filename FROM email_attachments WHERE email_id = %s "
                "ORDER BY filename",
                (saved.id,),
            )
            rows = cur.fetchall()
    assert [row[0] for row in rows] == ["invoice.pdf", "photo.png"]


def _insert_contact(user_id: str, email: str) -> str:
    """Insere um `crm_contacts` real para satisfazer a FK `emails.contact_id`."""
    contact_id = str(uuid.uuid4())
    with psycopg.connect(_uri()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO crm_contacts (id, user_id, name, email) "
                "VALUES (%s, %s, %s, %s)",
                (contact_id, user_id, "Test Contact", email),
            )
        conn.commit()
    return contact_id


async def test_upsert_email_persists_contact_id_when_provided() -> None:
    """email-client-imap-mvp-task-inbox-4-unit-1 (REQ-006): `contact_id`
    passado para `upsert_email` é persistido e retornado pela query."""
    from src.infrastructure.persistence.email_repository import (
        PostgresEmailRepository,
    )

    user_id = _insert_test_user()
    account_id = _insert_email_account(user_id)
    contact_id = _insert_contact(user_id, "linked@example.com")
    repo = PostgresEmailRepository(_uri())
    message = _parsed_message(
        message_id="msg-contact-linked@example.com",
        from_address="linked@example.com",
    )

    saved = await repo.upsert_email(account_id, message, contact_id=contact_id)

    assert saved.contact_id == contact_id
    stored = await repo.list_by_account(user_id, account_id, "INBOX", limit=10, offset=0)
    assert stored[0].contact_id == contact_id


async def test_upsert_email_preserves_existing_contact_id_when_re_upserted_without_one() -> None:
    """email-client-imap-mvp-task-inbox-4-unit-1 (REQ-006): re-upsert sem
    `contact_id` mantém o link existente (não desassocia)."""
    from src.infrastructure.persistence.email_repository import (
        PostgresEmailRepository,
    )

    user_id = _insert_test_user()
    account_id = _insert_email_account(user_id)
    contact_id = _insert_contact(user_id, "linked2@example.com")
    repo = PostgresEmailRepository(_uri())
    message = _parsed_message(
        message_id="msg-keep-link@example.com",
        from_address="linked2@example.com",
    )

    await repo.upsert_email(account_id, message, contact_id=contact_id)
    second = await repo.upsert_email(account_id, message)

    assert second.contact_id == contact_id


async def test_mark_read_flips_is_read_for_owned_email() -> None:
    """REQ-004 email-inbox: `mark_read` seta `is_read=true` contra Postgres real
    (regressão — a versão anterior usava `UPDATE ... JOIN`, sintaxe inválida em
    Postgres, e só falhava em runtime porque nenhum teste rodava contra um
    banco real; `SendEmail` passou a chamar `mark_read` e expôs o erro)."""
    from src.infrastructure.persistence.email_repository import (
        PostgresEmailRepository,
    )

    user_id = _insert_test_user()
    account_id = _insert_email_account(user_id)
    repo = PostgresEmailRepository(_uri())
    message = _parsed_message(message_id="msg-mark-read@example.com")
    saved = await repo.upsert_email(account_id, message)
    assert saved.is_read is False

    updated = await repo.mark_read(user_id, saved.id)

    assert updated is True
    refetched = await repo.get(user_id, saved.id)
    assert refetched is not None
    assert refetched.is_read is True


async def test_mark_read_returns_false_for_other_users_email() -> None:
    """REQ-002 email-inbox: cross-user `mark_read` não atualiza nem levanta."""
    from src.infrastructure.persistence.email_repository import (
        PostgresEmailRepository,
    )

    owner_id = _insert_test_user()
    other_id = _insert_test_user()
    account_id = _insert_email_account(owner_id)
    repo = PostgresEmailRepository(_uri())
    saved = await repo.upsert_email(
        account_id, _parsed_message(message_id="msg-cross-user@example.com")
    )

    updated = await repo.mark_read(other_id, saved.id)

    assert updated is False
    refetched = await repo.get(owner_id, saved.id)
    assert refetched is not None
    assert refetched.is_read is False


async def test_move_folder_updates_folder_for_owned_email() -> None:
    """REQ-004 email-inbox: `move_folder` move um email owned para outra pasta
    (mesma regressão de sintaxe `UPDATE ... JOIN` corrigida em `mark_read`)."""
    from src.infrastructure.persistence.email_repository import (
        PostgresEmailRepository,
    )

    user_id = _insert_test_user()
    account_id = _insert_email_account(user_id)
    repo = PostgresEmailRepository(_uri())
    saved = await repo.upsert_email(
        account_id, _parsed_message(message_id="msg-move-folder@example.com", folder="INBOX")
    )

    moved = await repo.move_folder(user_id, saved.id, "Archive")

    assert moved is True
    refetched = await repo.get(user_id, saved.id)
    assert refetched is not None
    assert refetched.folder == "Archive"
