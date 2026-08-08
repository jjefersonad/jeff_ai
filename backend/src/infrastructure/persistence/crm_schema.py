"""Schema Postgres das tabelas CRM (`crm_*`).

DDL idempotente via `psycopg` puro, mesmo padrão de
`user_integrations_schema` / `scheduled_tasks_schema`. Tabelas
escopadas por `user_id` (FK `users`), soft-archive via `archived_at`,
CHECKs de contato (email OU phone) e nota (exatamente um alvo).

Extensão `extend-crm-fields-location-value-custom`: city/state/custom_values,
`crm_field_definitions`, `crm_notes.archived_at`.
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
    city TEXT,
    state TEXT,
    custom_values JSONB NOT NULL DEFAULT '{}'::jsonb,
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
    city TEXT,
    state TEXT,
    custom_values JSONB NOT NULL DEFAULT '{}'::jsonb,
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
    custom_values JSONB NOT NULL DEFAULT '{}'::jsonb,
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
    archived_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT crm_notes_exactly_one_target_check
        CHECK (
            (contact_id IS NOT NULL)::int + (company_id IS NOT NULL)::int +
            (deal_id IS NOT NULL)::int = 1
        )
)
"""

_CREATE_CRM_FIELD_DEFINITIONS = """
CREATE TABLE IF NOT EXISTS crm_field_definitions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    entity TEXT NOT NULL CHECK (entity IN ('contact', 'company', 'deal')),
    key TEXT NOT NULL,
    label TEXT NOT NULL,
    field_type TEXT NOT NULL CHECK (field_type IN ('text', 'number', 'boolean')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT crm_field_definitions_user_entity_key_uq
        UNIQUE (user_id, entity, key)
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

_CREATE_CRM_FIELD_DEFINITIONS_USER_ENTITY_IDX = """
CREATE INDEX IF NOT EXISTS crm_field_definitions_user_entity_idx
    ON crm_field_definitions (user_id, entity)
"""

# Bancos criados antes desta change: CREATE TABLE IF NOT EXISTS não altera
# tabelas existentes — ADD COLUMN IF NOT EXISTS cobre a migração.
_ALTER_STATEMENTS = (
    "ALTER TABLE crm_companies ADD COLUMN IF NOT EXISTS city TEXT",
    "ALTER TABLE crm_companies ADD COLUMN IF NOT EXISTS state TEXT",
    "ALTER TABLE crm_companies "
    "ADD COLUMN IF NOT EXISTS custom_values JSONB NOT NULL DEFAULT '{}'::jsonb",
    "ALTER TABLE crm_contacts ADD COLUMN IF NOT EXISTS city TEXT",
    "ALTER TABLE crm_contacts ADD COLUMN IF NOT EXISTS state TEXT",
    "ALTER TABLE crm_contacts "
    "ADD COLUMN IF NOT EXISTS custom_values JSONB NOT NULL DEFAULT '{}'::jsonb",
    "ALTER TABLE crm_deals "
    "ADD COLUMN IF NOT EXISTS custom_values JSONB NOT NULL DEFAULT '{}'::jsonb",
    "ALTER TABLE crm_notes ADD COLUMN IF NOT EXISTS archived_at TIMESTAMPTZ",
)


def ensure_crm_schema(conninfo: str) -> None:
    """Cria/estende as tabelas CRM e índices de forma idempotente."""
    with psycopg.connect(conninfo, autocommit=True) as conn:
        with conn.cursor() as cur:
            # Ordem: companies → contacts → deals → notes (FKs) → definitions.
            cur.execute(_CREATE_CRM_COMPANIES)
            cur.execute(_CREATE_CRM_CONTACTS)
            cur.execute(_CREATE_CRM_DEALS)
            cur.execute(_CREATE_CRM_NOTES)
            cur.execute(_CREATE_CRM_FIELD_DEFINITIONS)
            for statement in _ALTER_STATEMENTS:
                cur.execute(statement)
            cur.execute(_CREATE_CRM_COMPANIES_USER_ID_IDX)
            cur.execute(_CREATE_CRM_CONTACTS_USER_ID_IDX)
            cur.execute(_CREATE_CRM_DEALS_USER_ID_IDX)
            cur.execute(_CREATE_CRM_NOTES_USER_ID_IDX)
            cur.execute(_CREATE_CRM_FIELD_DEFINITIONS_USER_ENTITY_IDX)


# Alias alinhado aos outros módulos (`ensure_schema`).
ensure_schema = ensure_crm_schema
