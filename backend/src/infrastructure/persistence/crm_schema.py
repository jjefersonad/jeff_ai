"""Schema Postgres das tabelas CRM (`crm_*`).

DDL idempotente via `psycopg` puro, mesmo padrão de
`user_integrations_schema` / `scheduled_tasks_schema`. Quatro tabelas
escopadas por `user_id` (FK `users`), soft-archive via `archived_at`,
CHECKs de contato (email OU phone) e nota (exatamente um alvo).
"""
from __future__ import annotations

import psycopg

_CREATE_CRM_COMPANIES = """
CREATE TABLE IF NOT EXISTS crm_companies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    name TEXT NOT NULL,
    website TEXT,
    domain TEXT,
    phone TEXT,
    notes TEXT,
    archived_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""

_CREATE_CRM_CONTACTS = """
CREATE TABLE IF NOT EXISTS crm_contacts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    name TEXT NOT NULL,
    email TEXT,
    phone TEXT,
    company_id UUID REFERENCES crm_companies(id),
    status TEXT,
    tags TEXT[] NOT NULL DEFAULT '{}',
    archived_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT crm_contacts_email_or_phone_check
        CHECK (email IS NOT NULL OR phone IS NOT NULL)
)
"""

_CREATE_CRM_DEALS = """
CREATE TABLE IF NOT EXISTS crm_deals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    title TEXT NOT NULL,
    stage TEXT NOT NULL DEFAULT 'lead',
    value NUMERIC,
    currency TEXT,
    contact_id UUID REFERENCES crm_contacts(id),
    company_id UUID REFERENCES crm_companies(id),
    archived_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""

_CREATE_CRM_NOTES = """
CREATE TABLE IF NOT EXISTS crm_notes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    body TEXT NOT NULL,
    source TEXT NOT NULL CHECK (source IN ('user', 'agent')),
    contact_id UUID REFERENCES crm_contacts(id),
    company_id UUID REFERENCES crm_companies(id),
    deal_id UUID REFERENCES crm_deals(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT crm_notes_exactly_one_target_check
        CHECK (
            (contact_id IS NOT NULL)::int + (company_id IS NOT NULL)::int +
            (deal_id IS NOT NULL)::int = 1
        )
)
"""

_CREATE_CRM_COMPANIES_USER_ID_IDX = """
CREATE INDEX IF NOT EXISTS crm_companies_user_id_idx
    ON crm_companies (user_id)
"""

_CREATE_CRM_CONTACTS_USER_ID_IDX = """
CREATE INDEX IF NOT EXISTS crm_contacts_user_id_idx
    ON crm_contacts (user_id)
"""

_CREATE_CRM_DEALS_USER_ID_IDX = """
CREATE INDEX IF NOT EXISTS crm_deals_user_id_idx
    ON crm_deals (user_id)
"""

_CREATE_CRM_NOTES_USER_ID_IDX = """
CREATE INDEX IF NOT EXISTS crm_notes_user_id_idx
    ON crm_notes (user_id)
"""


def ensure_crm_schema(conninfo: str) -> None:
    """Cria as tabelas CRM e índices de forma idempotente."""
    with psycopg.connect(conninfo, autocommit=True) as conn:
        with conn.cursor() as cur:
            # Ordem: companies → contacts → deals → notes (FKs).
            cur.execute(_CREATE_CRM_COMPANIES)
            cur.execute(_CREATE_CRM_CONTACTS)
            cur.execute(_CREATE_CRM_DEALS)
            cur.execute(_CREATE_CRM_NOTES)
            cur.execute(_CREATE_CRM_COMPANIES_USER_ID_IDX)
            cur.execute(_CREATE_CRM_CONTACTS_USER_ID_IDX)
            cur.execute(_CREATE_CRM_DEALS_USER_ID_IDX)
            cur.execute(_CREATE_CRM_NOTES_USER_ID_IDX)


# Alias alinhado aos outros módulos (`ensure_schema`).
ensure_schema = ensure_crm_schema
