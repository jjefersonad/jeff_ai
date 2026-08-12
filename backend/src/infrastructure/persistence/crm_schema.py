"""Schema Postgres das tabelas CRM (`crm_*`).

DDL idempotente via `psycopg` puro, mesmo padrão de
`user_integrations_schema` / `scheduled_tasks_schema`. Tabelas
escopadas por `user_id` (FK `users`), soft-archive via `archived_at`,
CHECKs de contato (email OU phone) e nota (exatamente um alvo).

Extensão `extend-crm-fields-location-value-custom`: city/state/custom_values,
`crm_field_definitions`, `crm_notes.archived_at`.

Extensão `sales-pipeline-via-agent`: `crm_leads` (triagem isolada de contato/empresa/deal,
CHECK exige email OU phone OU company_name); `source_lead_id` em
`crm_deals`/`crm_contacts`/`crm_companies` (rastreia a conversão de origem);
`crm_deals.stage` perde `'lead'` do domínio (lead agora é entidade própria) e
ganha `'negotiation'` — migração via drop+recreate do CHECK nomeado, mesmo
padrão de `scheduled_tasks_schema._MIGRATE_STATUS_CHECK_WAITING_HUMAN`.
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
    stage TEXT NOT NULL DEFAULT 'qualified'
        CONSTRAINT crm_deals_stage_check
        CHECK (stage IN ('qualified', 'proposal', 'negotiation', 'won', 'lost')),
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

_CREATE_CRM_LEADS = """
CREATE TABLE IF NOT EXISTS crm_leads (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    name TEXT NOT NULL,
    email TEXT,
    phone TEXT,
    company_name TEXT,
    interest TEXT,
    estimated_value NUMERIC,
    currency TEXT,
    qualification_score SMALLINT CHECK (qualification_score BETWEEN 0 AND 100),
    notes TEXT,
    status TEXT NOT NULL DEFAULT 'new'
        CHECK (status IN ('new', 'contacted', 'qualified', 'discarded')),
    tags TEXT[] NOT NULL DEFAULT '{}',
    custom_values JSONB NOT NULL DEFAULT '{}'::jsonb,
    source TEXT
        CHECK (source IN ('manual', 'form', 'referral', 'instagram', 'import', 'other')),
    converted_at TIMESTAMPTZ,
    converted_contact_id UUID REFERENCES crm_contacts(id),
    converted_company_id UUID REFERENCES crm_companies(id),
    converted_deal_id UUID REFERENCES crm_deals(id),
    archived_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT crm_leads_contact_info_check
        CHECK (email IS NOT NULL OR phone IS NOT NULL OR company_name IS NOT NULL)
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

_CREATE_CRM_LEADS_USER_ID_IDX = """
CREATE INDEX IF NOT EXISTS crm_leads_user_id_idx
    ON crm_leads (user_id)
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
    "ALTER TABLE crm_deals "
    "ADD COLUMN IF NOT EXISTS source_lead_id UUID REFERENCES crm_leads(id)",
    "ALTER TABLE crm_contacts "
    "ADD COLUMN IF NOT EXISTS source_lead_id UUID REFERENCES crm_leads(id)",
    "ALTER TABLE crm_companies "
    "ADD COLUMN IF NOT EXISTS source_lead_id UUID REFERENCES crm_leads(id)",
    "ALTER TABLE crm_deals ALTER COLUMN stage SET DEFAULT 'qualified'",
)

# Bancos criados antes de sales-pipeline-via-agent não têm NENHUM CHECK em
# `stage` (a coluna só tinha DEFAULT) ou têm um CHECK antigo com `lead` e sem
# `negotiation`. CREATE TABLE IF NOT EXISTS não altera CHECK/coluna
# existente — drop (se houver um antigo) + add (se o correto ainda não
# existe), idempotente nos restarts seguintes. Mesmo padrão de
# `scheduled_tasks_schema._MIGRATE_STATUS_CHECK_WAITING_HUMAN`, estendido
# para cobrir o caso de a coluna nunca ter tido CHECK nenhum.
_MIGRATE_DEALS_STAGE_CHECK = """
DO $$
DECLARE
    old_stage_check TEXT;
BEGIN
    SELECT con.conname INTO old_stage_check
    FROM pg_constraint con
    JOIN pg_class rel ON rel.oid = con.conrelid
    JOIN pg_namespace nsp ON nsp.oid = rel.relnamespace
    WHERE rel.relname = 'crm_deals'
      AND nsp.nspname = current_schema()
      AND con.contype = 'c'
      AND pg_get_constraintdef(con.oid) LIKE '%stage%'
      AND pg_get_constraintdef(con.oid) NOT LIKE '%negotiation%';

    IF old_stage_check IS NOT NULL THEN
        EXECUTE format(
            'ALTER TABLE crm_deals DROP CONSTRAINT %I',
            old_stage_check
        );
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint con
        JOIN pg_class rel ON rel.oid = con.conrelid
        JOIN pg_namespace nsp ON nsp.oid = rel.relnamespace
        WHERE rel.relname = 'crm_deals'
          AND nsp.nspname = current_schema()
          AND con.contype = 'c'
          AND pg_get_constraintdef(con.oid) LIKE '%stage%'
          AND pg_get_constraintdef(con.oid) LIKE '%negotiation%'
    ) THEN
        ALTER TABLE crm_deals
            ADD CONSTRAINT crm_deals_stage_check
            CHECK (stage IN (
                'qualified', 'proposal', 'negotiation', 'won', 'lost'
            ));
    END IF;
END $$
"""


def ensure_crm_schema(conninfo: str) -> None:
    """Cria/estende as tabelas CRM e índices de forma idempotente."""
    with psycopg.connect(conninfo, autocommit=True) as conn:
        with conn.cursor() as cur:
            # Ordem: companies → contacts → deals → leads (FKs) → notes → definitions.
            cur.execute(_CREATE_CRM_COMPANIES)
            cur.execute(_CREATE_CRM_CONTACTS)
            cur.execute(_CREATE_CRM_DEALS)
            cur.execute(_CREATE_CRM_LEADS)
            cur.execute(_CREATE_CRM_NOTES)
            cur.execute(_CREATE_CRM_FIELD_DEFINITIONS)
            for statement in _ALTER_STATEMENTS:
                cur.execute(statement)
            cur.execute(_MIGRATE_DEALS_STAGE_CHECK)
            cur.execute(_CREATE_CRM_COMPANIES_USER_ID_IDX)
            cur.execute(_CREATE_CRM_CONTACTS_USER_ID_IDX)
            cur.execute(_CREATE_CRM_DEALS_USER_ID_IDX)
            cur.execute(_CREATE_CRM_LEADS_USER_ID_IDX)
            cur.execute(_CREATE_CRM_NOTES_USER_ID_IDX)
            cur.execute(_CREATE_CRM_FIELD_DEFINITIONS_USER_ENTITY_IDX)


# Alias alinhado aos outros módulos (`ensure_schema`).
ensure_schema = ensure_crm_schema
