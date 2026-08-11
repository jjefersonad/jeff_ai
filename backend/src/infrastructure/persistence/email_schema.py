"""Schema Postgres das tabelas de email (`email_accounts`/`emails`/`email_attachments`).

DDL idempotente via `psycopg` puro, mesmo padrão de `crm_schema`/
`user_integrations_schema`. `email_accounts` guarda metadata de baixa
sensibilidade e alta frequência de escrita (status, `last_synced_at`),
separada da tabela `user_integrations` (que guarda os segredos cifrados por
campo) via `user_integration_id` — design Decision 1 de
`email-client-imap-mvp`: evita recifrar segredos a cada heartbeat de sync.
`emails.contact_id` associa uma mensagem a um `crm_contacts` existente (REQ-006
do spec `email-inbox`), sem exigir nenhuma tabela nova no CRM.
"""
from __future__ import annotations

import psycopg

_CREATE_EMAIL_ACCOUNTS = """
CREATE TABLE IF NOT EXISTS email_accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    user_integration_id UUID NOT NULL REFERENCES user_integrations(id),
    provider TEXT NOT NULL DEFAULT 'imap',
    display_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'connected',
    last_synced_at TIMESTAMPTZ,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT email_accounts_status_check
        CHECK (status IN ('connected', 'error', 'syncing'))
)
"""

_CREATE_EMAILS = """
CREATE TABLE IF NOT EXISTS emails (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email_account_id UUID NOT NULL REFERENCES email_accounts(id),
    message_id TEXT NOT NULL,
    thread_id TEXT,
    folder TEXT NOT NULL,
    from_address TEXT NOT NULL,
    from_name TEXT,
    to_addresses JSONB NOT NULL DEFAULT '[]'::jsonb,
    cc_addresses JSONB NOT NULL DEFAULT '[]'::jsonb,
    bcc_addresses JSONB NOT NULL DEFAULT '[]'::jsonb,
    subject TEXT,
    body_html TEXT,
    body_text TEXT,
    is_read BOOLEAN NOT NULL DEFAULT false,
    is_starred BOOLEAN NOT NULL DEFAULT false,
    has_attachments BOOLEAN NOT NULL DEFAULT false,
    contact_id UUID REFERENCES crm_contacts(id),
    received_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT emails_account_message_id_uq
        UNIQUE (email_account_id, message_id)
)
"""

_CREATE_EMAIL_ATTACHMENTS = """
CREATE TABLE IF NOT EXISTS email_attachments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email_id UUID NOT NULL REFERENCES emails(id),
    filename TEXT NOT NULL,
    mime_type TEXT,
    size_bytes BIGINT,
    storage_path TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""

_CREATE_EMAIL_ACCOUNTS_USER_ID_IDX = """
CREATE INDEX IF NOT EXISTS email_accounts_user_id_idx
    ON email_accounts (user_id)
"""

_CREATE_EMAILS_ACCOUNT_ID_IDX = """
CREATE INDEX IF NOT EXISTS emails_email_account_id_idx
    ON emails (email_account_id)
"""

_CREATE_EMAILS_CONTACT_ID_IDX = """
CREATE INDEX IF NOT EXISTS emails_contact_id_idx
    ON emails (contact_id)
"""

_CREATE_EMAIL_ATTACHMENTS_EMAIL_ID_IDX = """
CREATE INDEX IF NOT EXISTS email_attachments_email_id_idx
    ON email_attachments (email_id)
"""


def ensure_email_schema(conninfo: str) -> None:
    """Cria as tabelas de email e seus índices de forma idempotente."""
    with psycopg.connect(conninfo, autocommit=True) as conn:
        with conn.cursor() as cur:
            # Ordem: accounts → emails (FK) → attachments (FK).
            cur.execute(_CREATE_EMAIL_ACCOUNTS)
            cur.execute(_CREATE_EMAILS)
            cur.execute(_CREATE_EMAIL_ATTACHMENTS)
            cur.execute(_CREATE_EMAIL_ACCOUNTS_USER_ID_IDX)
            cur.execute(_CREATE_EMAILS_ACCOUNT_ID_IDX)
            cur.execute(_CREATE_EMAILS_CONTACT_ID_IDX)
            cur.execute(_CREATE_EMAIL_ATTACHMENTS_EMAIL_ID_IDX)


# Alias alinhado aos outros módulos (`ensure_schema`).
ensure_schema = ensure_email_schema
