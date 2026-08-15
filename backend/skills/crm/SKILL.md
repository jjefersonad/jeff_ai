---
name: crm
description: "Use this skill for the Jeff AI native CRM only (tools whose names start with crm_: crm_search_contacts, crm_upsert_contact, crm_add_note, crm_list_deals, crm_create_deal, crm_move_deal, crm_list_field_definitions, crm_create_field_definition, crm_update_field_definition). Triggers: CRM Jeff AI, /crm, cadastrar lead no CRM, deal, funil, contato Jeff AI, follow-up no CRM, campo personalizado CRM. NEVER use MCP tools contacts_*, lead_gen_*, sequences_* for this — those are a different external platform. NÃO use para: agenda (scheduling), memória genérica, sync WhatsApp."
---

# CRM Skill (Jeff AI nativo)

O CRM do Jeff AI é o módulo de produto em `/crm` (Postgres + `/api/crm/*`).
Tools flat cujo nome **sempre** começa com `crm_`. Não existe `crm_subagent`
nem mode `crm`. Ownership vem da sessão (`resolve_user_id`); nunca passe
`user_id`.

## Separação crítica — MCP externo ≠ CRM Jeff AI

Se aparecerem tools como `contacts_list_contacts`, `lead_gen_list_leads`,
`sequences_enroll_contacts` ou `mcp__…`, elas são de **outra plataforma**
(MCP). Para cadastrar lead / contato / deal na UI Jeff AI (`/crm`), use
**apenas**:

| Tool | Quando usar |
|------|-------------|
| `crm_search_contacts` | Buscar/listar contatos (`query`, opcional `company_id`) |
| `crm_upsert_contact` | Criar (sem `contact_id`) ou atualizar. Exige email e/ou phone. Aceita `city`/`state`/`custom_values` |
| `crm_add_note` | Follow-up; exatamente um alvo; `source=agent` |
| `crm_list_deals` | Listar deals do funil |
| `crm_create_deal` | Abrir oportunidade (default stage = `lead`; `value`/`custom_values`) |
| `crm_move_deal` | Mover estágio |
| `crm_list_field_definitions` | Listar campos personalizados (`entity` opcional) — **sempre antes de criar** |
| `crm_create_field_definition` | Criar definição nova (`entity`, `key`, `label`, `field_type`) |
| `crm_update_field_definition` | Atualizar só o `label` (key/tipo imutáveis) |

## Campos personalizados

Tipos na v1: `text` | `number` | `boolean`. Entidades: `contact` | `company` | `deal`.

1. `crm_list_field_definitions(entity=…)` — reutilize a `key` existente.
2. Só se não existir: `crm_create_field_definition(…)` com `key` slug
   (`^[a-z][a-z0-9_]*$`) e `label` livre.
3. Grave valores via `custom_values` em `crm_upsert_contact` /
   `crm_create_deal` (chave deve existir na definição).

Não invente chaves novas a cada lead; otimize o modelo do usuário.

## Funil (estágios fixos)

`lead` → `qualified` → `proposal` → `won` / `lost`

## Fluxo: cadastrar LEAD

1. Opcional: pesquisar o perfil (internet/memória) — não grava no CRM.
2. `crm_upsert_contact(name=…, email=…, city=…)` (ou phone).
3. `crm_create_deal(title=…, stage="lead", contact_id=<id>, value=…)`.
4. Opcional: `crm_add_note(body=…, contact_id=…)` ou `deal_id=…`.

Confirme os ids retornados — o registro aparece na UI `/crm`.

## Regras

- Sem identidade de sessão → tools retornam erro.
- Notas são imutáveis após criação.
- Nunca diga que usou o CRM Jeff AI se chamou só MCP `contacts_*`/`lead_gen_*`.
