"""Adapter Postgres de `CrmRepositoryPort`.

Todas as queries filtram por `user_id`. Miss cross-user → `None` / lista vazia.
Padrão: `psycopg` async, uma conexão por operação.
"""
from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import psycopg
from psycopg.errors import UniqueViolation

from src.application.ports.crm_repository import (
    ContactPage,
    CrmRepositoryPort,
    LeadConversionResult,
)
from src.domain.crm import (
    Company,
    Contact,
    Deal,
    DealStage,
    DuplicateFieldDefinitionError,
    FieldDefinition,
    FieldEntity,
    FieldType,
    Lead,
    LeadSource,
    LeadStatus,
    Note,
    NoteSource,
)

_CONTACT_COLUMNS = (
    "id, user_id, name, email, phone, company_id, status, tags, "
    "city, state, custom_values, source_lead_id, archived_at, created_at, "
    "updated_at"
)
_COMPANY_COLUMNS = (
    "id, user_id, name, website, domain, phone, notes, "
    "city, state, custom_values, source_lead_id, archived_at, created_at, "
    "updated_at"
)
_DEAL_COLUMNS = (
    "id, user_id, title, stage, value, currency, contact_id, company_id, "
    "custom_values, source_lead_id, archived_at, created_at, updated_at"
)
_NOTE_COLUMNS = (
    "id, user_id, body, source, contact_id, company_id, deal_id, "
    "archived_at, created_at"
)
_LEAD_COLUMNS = (
    "id, user_id, name, email, phone, company_name, interest, "
    "estimated_value, currency, qualification_score, notes, status, tags, "
    "custom_values, source, converted_at, converted_contact_id, "
    "converted_company_id, converted_deal_id, archived_at, created_at, "
    "updated_at"
)
_FIELD_DEF_COLUMNS = (
    "id, user_id, entity, key, label, field_type, created_at, updated_at"
)


def _as_jsonb(value: dict[str, Any] | None) -> str:
    return json.dumps(value or {})


def _row_to_contact(row: tuple[Any, ...]) -> Contact:
    (
        contact_id,
        user_id,
        name,
        email,
        phone,
        company_id,
        status,
        tags,
        city,
        state,
        custom_values,
        source_lead_id,
        archived_at,
        created_at,
        updated_at,
    ) = row
    return Contact(
        id=str(contact_id),
        user_id=str(user_id),
        name=name,
        email=email,
        phone=phone,
        company_id=str(company_id) if company_id is not None else None,
        status=status,
        tags=list(tags) if tags is not None else [],
        city=city,
        state=state,
        custom_values=dict(custom_values or {}),
        source_lead_id=str(source_lead_id) if source_lead_id is not None else None,
        archived_at=archived_at,
        created_at=created_at,
        updated_at=updated_at,
    )


def _row_to_company(row: tuple[Any, ...]) -> Company:
    (
        company_id,
        user_id,
        name,
        website,
        domain,
        phone,
        notes,
        city,
        state,
        custom_values,
        source_lead_id,
        archived_at,
        created_at,
        updated_at,
    ) = row
    return Company(
        id=str(company_id),
        user_id=str(user_id),
        name=name,
        website=website,
        domain=domain,
        phone=phone,
        notes=notes,
        city=city,
        state=state,
        custom_values=dict(custom_values or {}),
        source_lead_id=str(source_lead_id) if source_lead_id is not None else None,
        archived_at=archived_at,
        created_at=created_at,
        updated_at=updated_at,
    )


def _row_to_deal(row: tuple[Any, ...]) -> Deal:
    (
        deal_id,
        user_id,
        title,
        stage,
        value,
        currency,
        contact_id,
        company_id,
        custom_values,
        source_lead_id,
        archived_at,
        created_at,
        updated_at,
    ) = row
    return Deal(
        id=str(deal_id),
        user_id=str(user_id),
        title=title,
        stage=DealStage(stage),
        value=Decimal(str(value)) if value is not None else None,
        currency=currency,
        contact_id=str(contact_id) if contact_id is not None else None,
        company_id=str(company_id) if company_id is not None else None,
        custom_values=dict(custom_values or {}),
        source_lead_id=str(source_lead_id) if source_lead_id is not None else None,
        archived_at=archived_at,
        created_at=created_at,
        updated_at=updated_at,
    )


def _row_to_note(row: tuple[Any, ...]) -> Note:
    (
        note_id,
        user_id,
        body,
        source,
        contact_id,
        company_id,
        deal_id,
        archived_at,
        created_at,
    ) = row
    return Note(
        id=str(note_id),
        user_id=str(user_id),
        body=body,
        source=NoteSource(source),
        contact_id=str(contact_id) if contact_id is not None else None,
        company_id=str(company_id) if company_id is not None else None,
        deal_id=str(deal_id) if deal_id is not None else None,
        archived_at=archived_at,
        created_at=created_at,
    )


def _row_to_lead(row: tuple[Any, ...]) -> Lead:
    (
        lead_id,
        user_id,
        name,
        email,
        phone,
        company_name,
        interest,
        estimated_value,
        currency,
        qualification_score,
        notes,
        status,
        tags,
        custom_values,
        source,
        converted_at,
        converted_contact_id,
        converted_company_id,
        converted_deal_id,
        archived_at,
        created_at,
        updated_at,
    ) = row
    return Lead(
        id=str(lead_id),
        user_id=str(user_id),
        name=name,
        email=email,
        phone=phone,
        company_name=company_name,
        interest=interest,
        estimated_value=Decimal(str(estimated_value))
        if estimated_value is not None
        else None,
        currency=currency,
        qualification_score=qualification_score,
        notes=notes,
        status=LeadStatus(status),
        tags=list(tags) if tags is not None else [],
        custom_values=dict(custom_values or {}),
        source=LeadSource(source) if source is not None else None,
        converted_at=converted_at,
        converted_contact_id=str(converted_contact_id)
        if converted_contact_id is not None
        else None,
        converted_company_id=str(converted_company_id)
        if converted_company_id is not None
        else None,
        converted_deal_id=str(converted_deal_id)
        if converted_deal_id is not None
        else None,
        archived_at=archived_at,
        created_at=created_at,
        updated_at=updated_at,
    )


def _row_to_field_definition(row: tuple[Any, ...]) -> FieldDefinition:
    (
        definition_id,
        user_id,
        entity,
        key,
        label,
        field_type,
        created_at,
        updated_at,
    ) = row
    return FieldDefinition(
        id=str(definition_id),
        user_id=str(user_id),
        entity=FieldEntity(entity),
        key=key,
        label=label,
        field_type=FieldType(field_type),
        created_at=created_at,
        updated_at=updated_at,
    )


class PostgresCrmRepository(CrmRepositoryPort):
    """Persiste entidades CRM nas tabelas `crm_*`, sempre escopadas a `user_id`."""

    def __init__(self, conninfo: str) -> None:
        """Guarda o conninfo Postgres — uma conexão é aberta por operação."""
        self._conninfo = conninfo

    # --- Companies -----------------------------------------------------------

    async def create_company(self, company: Company) -> Company:
        """Insere empresa e devolve a linha persistida."""
        async with await psycopg.AsyncConnection.connect(self._conninfo) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    f"""
                    INSERT INTO crm_companies ({_COMPANY_COLUMNS})
                    VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s
                    )
                    RETURNING {_COMPANY_COLUMNS}
                    """,
                    (
                        company.id,
                        company.user_id,
                        company.name,
                        company.website,
                        company.domain,
                        company.phone,
                        company.notes,
                        company.city,
                        company.state,
                        _as_jsonb(company.custom_values),
                        company.source_lead_id,
                        company.archived_at,
                        company.created_at,
                        company.updated_at,
                    ),
                )
                row = await cur.fetchone()
            await conn.commit()
        assert row is not None
        return _row_to_company(row)

    async def get_company(self, user_id: str, company_id: str) -> Company | None:
        """Retorna empresa do user ou ``None``."""
        async with await psycopg.AsyncConnection.connect(self._conninfo) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    f"SELECT {_COMPANY_COLUMNS} FROM crm_companies "
                    "WHERE id = %s AND user_id = %s",
                    (company_id, user_id),
                )
                row = await cur.fetchone()
        return _row_to_company(row) if row is not None else None

    async def get_company_by_name(self, user_id: str, name: str) -> Company | None:
        """Match exato case-insensitive de `name` para uma empresa ativa do user."""
        async with await psycopg.AsyncConnection.connect(self._conninfo) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    f"SELECT {_COMPANY_COLUMNS} FROM crm_companies "
                    "WHERE user_id = %s AND archived_at IS NULL "
                    "AND LOWER(name) = LOWER(%s) LIMIT 1",
                    (user_id, name),
                )
                row = await cur.fetchone()
        return _row_to_company(row) if row is not None else None

    async def list_companies(
        self,
        user_id: str,
        *,
        query: str | None = None,
        include_archived: bool = False,
    ) -> list[Company]:
        """Lista empresas do user; busca opcional por nome/domínio."""
        clauses = ["user_id = %s"]
        params: list[object] = [user_id]
        if not include_archived:
            clauses.append("archived_at IS NULL")
        if query:
            clauses.append("(name ILIKE %s OR COALESCE(domain, '') ILIKE %s)")
            like = f"%{query}%"
            params.extend([like, like])
        where = " AND ".join(clauses)
        async with await psycopg.AsyncConnection.connect(self._conninfo) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    f"SELECT {_COMPANY_COLUMNS} FROM crm_companies "
                    f"WHERE {where} ORDER BY created_at DESC",
                    params,
                )
                rows = await cur.fetchall()
        return [_row_to_company(r) for r in rows]

    async def update_company(self, company: Company) -> Company | None:
        """Atualiza empresa própria; ``None`` se miss."""
        async with await psycopg.AsyncConnection.connect(self._conninfo) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    f"""
                    UPDATE crm_companies SET
                        name = %s, website = %s, domain = %s, phone = %s,
                        notes = %s, city = %s, state = %s,
                        custom_values = %s::jsonb, archived_at = %s, updated_at = %s
                    WHERE id = %s AND user_id = %s
                    RETURNING {_COMPANY_COLUMNS}
                    """,
                    (
                        company.name,
                        company.website,
                        company.domain,
                        company.phone,
                        company.notes,
                        company.city,
                        company.state,
                        _as_jsonb(company.custom_values),
                        company.archived_at,
                        company.updated_at,
                        company.id,
                        company.user_id,
                    ),
                )
                row = await cur.fetchone()
            await conn.commit()
        return _row_to_company(row) if row is not None else None

    async def archive_company(self, user_id: str, company_id: str) -> Company | None:
        """Arquiva (soft-delete); ``None`` se miss."""
        now = datetime.now(UTC)
        async with await psycopg.AsyncConnection.connect(self._conninfo) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    f"""
                    UPDATE crm_companies
                    SET archived_at = %s, updated_at = %s
                    WHERE id = %s AND user_id = %s
                    RETURNING {_COMPANY_COLUMNS}
                    """,
                    (now, now, company_id, user_id),
                )
                row = await cur.fetchone()
            await conn.commit()
        return _row_to_company(row) if row is not None else None

    # --- Contacts ------------------------------------------------------------

    async def create_contact(self, contact: Contact) -> Contact:
        """Insere contato e devolve a linha persistida."""
        async with await psycopg.AsyncConnection.connect(self._conninfo) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    f"""
                    INSERT INTO crm_contacts ({_CONTACT_COLUMNS})
                    VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s
                    )
                    RETURNING {_CONTACT_COLUMNS}
                    """,
                    (
                        contact.id,
                        contact.user_id,
                        contact.name,
                        contact.email,
                        contact.phone,
                        contact.company_id,
                        contact.status,
                        contact.tags,
                        contact.city,
                        contact.state,
                        _as_jsonb(contact.custom_values),
                        contact.source_lead_id,
                        contact.archived_at,
                        contact.created_at,
                        contact.updated_at,
                    ),
                )
                row = await cur.fetchone()
            await conn.commit()
        assert row is not None
        return _row_to_contact(row)

    async def get_contact(self, user_id: str, contact_id: str) -> Contact | None:
        """Retorna contato do user ou ``None``."""
        async with await psycopg.AsyncConnection.connect(self._conninfo) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    f"SELECT {_CONTACT_COLUMNS} FROM crm_contacts "
                    "WHERE id = %s AND user_id = %s",
                    (contact_id, user_id),
                )
                row = await cur.fetchone()
        return _row_to_contact(row) if row is not None else None

    async def get_contact_by_email(self, user_id: str, email: str) -> Contact | None:
        """Match exato case-insensitive de `email` para um contato do user.

        Filtra por `user_id` para nunca devolver contato de outro usuário
        (`email-client-imap-mvp` REQ-006). Em caso de múltiplos matches
        (sem UNIQUE constraint em `email`), retorna o mais recentemente
        atualizado (`updated_at DESC`) — escolha estável e alinhada ao
        ordenamento default de `list_contacts_page`.
        """
        async with await psycopg.AsyncConnection.connect(self._conninfo) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    f"SELECT {_CONTACT_COLUMNS} FROM crm_contacts "
                    "WHERE user_id = %s AND email IS NOT NULL "
                    "AND LOWER(email) = LOWER(%s) "
                    "ORDER BY updated_at DESC LIMIT 1",
                    (user_id, email),
                )
                row = await cur.fetchone()
        return _row_to_contact(row) if row is not None else None

    def _contact_filters(
        self,
        user_id: str,
        *,
        query: str | None,
        company_id: str | None,
        include_archived: bool,
    ) -> tuple[str, list[object]]:
        clauses = ["user_id = %s"]
        params: list[object] = [user_id]
        if not include_archived:
            clauses.append("archived_at IS NULL")
        if company_id is not None:
            clauses.append("company_id = %s")
            params.append(company_id)
        if query:
            clauses.append(
                "(name ILIKE %s OR COALESCE(email, '') ILIKE %s "
                "OR COALESCE(phone, '') ILIKE %s)"
            )
            like = f"%{query}%"
            params.extend([like, like, like])
        return " AND ".join(clauses), params

    async def list_contacts(
        self,
        user_id: str,
        *,
        query: str | None = None,
        company_id: str | None = None,
        include_archived: bool = False,
    ) -> list[Contact]:
        """Lista contatos do user; filtro opcional por termo/empresa."""
        page = await self.list_contacts_page(
            user_id,
            query=query,
            company_id=company_id,
            include_archived=include_archived,
            page=1,
            page_size=10_000,
        )
        return page.items

    async def list_contacts_page(
        self,
        user_id: str,
        *,
        query: str | None = None,
        company_id: str | None = None,
        include_archived: bool = False,
        page: int = 1,
        page_size: int = 20,
    ) -> ContactPage:
        """Lista paginada de contatos ordenada por updated_at DESC."""
        safe_page = max(1, page)
        safe_size = max(1, min(page_size, 100))
        where, params = self._contact_filters(
            user_id,
            query=query,
            company_id=company_id,
            include_archived=include_archived,
        )
        offset = (safe_page - 1) * safe_size
        async with await psycopg.AsyncConnection.connect(self._conninfo) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    f"SELECT COUNT(*) FROM crm_contacts WHERE {where}",
                    params,
                )
                count_row = await cur.fetchone()
                total = int(count_row[0]) if count_row is not None else 0
                await cur.execute(
                    f"SELECT {_CONTACT_COLUMNS} FROM crm_contacts "
                    f"WHERE {where} ORDER BY updated_at DESC "
                    f"LIMIT %s OFFSET %s",
                    [*params, safe_size, offset],
                )
                rows = await cur.fetchall()
        return ContactPage(items=[_row_to_contact(r) for r in rows], total=total)

    async def update_contact(self, contact: Contact) -> Contact | None:
        """Atualiza contato próprio; ``None`` se miss."""
        async with await psycopg.AsyncConnection.connect(self._conninfo) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    f"""
                    UPDATE crm_contacts SET
                        name = %s, email = %s, phone = %s, company_id = %s,
                        status = %s, tags = %s, city = %s, state = %s,
                        custom_values = %s::jsonb, archived_at = %s, updated_at = %s
                    WHERE id = %s AND user_id = %s
                    RETURNING {_CONTACT_COLUMNS}
                    """,
                    (
                        contact.name,
                        contact.email,
                        contact.phone,
                        contact.company_id,
                        contact.status,
                        contact.tags,
                        contact.city,
                        contact.state,
                        _as_jsonb(contact.custom_values),
                        contact.archived_at,
                        contact.updated_at,
                        contact.id,
                        contact.user_id,
                    ),
                )
                row = await cur.fetchone()
            await conn.commit()
        return _row_to_contact(row) if row is not None else None

    async def archive_contact(self, user_id: str, contact_id: str) -> Contact | None:
        """Arquiva contato e soft-arquiva notes/deals do mesmo user vinculados."""
        now = datetime.now(UTC)
        async with await psycopg.AsyncConnection.connect(self._conninfo) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    f"""
                    UPDATE crm_contacts
                    SET archived_at = %s, updated_at = %s
                    WHERE id = %s AND user_id = %s
                    RETURNING {_CONTACT_COLUMNS}
                    """,
                    (now, now, contact_id, user_id),
                )
                row = await cur.fetchone()
                if row is None:
                    await conn.commit()
                    return None
                await cur.execute(
                    """
                    UPDATE crm_deals
                    SET archived_at = %s, updated_at = %s
                    WHERE contact_id = %s AND user_id = %s AND archived_at IS NULL
                    """,
                    (now, now, contact_id, user_id),
                )
                await cur.execute(
                    """
                    UPDATE crm_notes
                    SET archived_at = %s
                    WHERE contact_id = %s AND user_id = %s AND archived_at IS NULL
                    """,
                    (now, contact_id, user_id),
                )
            await conn.commit()
        return _row_to_contact(row)

    # --- Deals ---------------------------------------------------------------

    async def create_deal(self, deal: Deal) -> Deal:
        """Insere deal e devolve a linha persistida."""
        async with await psycopg.AsyncConnection.connect(self._conninfo) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    f"""
                    INSERT INTO crm_deals ({_DEAL_COLUMNS})
                    VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s
                    )
                    RETURNING {_DEAL_COLUMNS}
                    """,
                    (
                        deal.id,
                        deal.user_id,
                        deal.title,
                        deal.stage.value,
                        deal.value,
                        deal.currency,
                        deal.contact_id,
                        deal.company_id,
                        _as_jsonb(deal.custom_values),
                        deal.source_lead_id,
                        deal.archived_at,
                        deal.created_at,
                        deal.updated_at,
                    ),
                )
                row = await cur.fetchone()
            await conn.commit()
        assert row is not None
        return _row_to_deal(row)

    async def get_deal(self, user_id: str, deal_id: str) -> Deal | None:
        """Retorna deal do user ou ``None``."""
        async with await psycopg.AsyncConnection.connect(self._conninfo) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    f"SELECT {_DEAL_COLUMNS} FROM crm_deals "
                    "WHERE id = %s AND user_id = %s",
                    (deal_id, user_id),
                )
                row = await cur.fetchone()
        return _row_to_deal(row) if row is not None else None

    async def list_deals(
        self,
        user_id: str,
        *,
        stage: DealStage | None = None,
        include_archived: bool = False,
    ) -> list[Deal]:
        """Lista deals do user; filtro opcional por estágio."""
        clauses = ["user_id = %s"]
        params: list[object] = [user_id]
        if not include_archived:
            clauses.append("archived_at IS NULL")
        if stage is not None:
            clauses.append("stage = %s")
            params.append(stage.value)
        where = " AND ".join(clauses)
        async with await psycopg.AsyncConnection.connect(self._conninfo) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    f"SELECT {_DEAL_COLUMNS} FROM crm_deals "
                    f"WHERE {where} ORDER BY created_at DESC",
                    params,
                )
                rows = await cur.fetchall()
        return [_row_to_deal(r) for r in rows]

    async def update_deal(self, deal: Deal) -> Deal | None:
        """Atualiza deal próprio; ``None`` se miss."""
        async with await psycopg.AsyncConnection.connect(self._conninfo) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    f"""
                    UPDATE crm_deals SET
                        title = %s, stage = %s, value = %s, currency = %s,
                        contact_id = %s, company_id = %s,
                        custom_values = %s::jsonb, archived_at = %s, updated_at = %s
                    WHERE id = %s AND user_id = %s
                    RETURNING {_DEAL_COLUMNS}
                    """,
                    (
                        deal.title,
                        deal.stage.value,
                        deal.value,
                        deal.currency,
                        deal.contact_id,
                        deal.company_id,
                        _as_jsonb(deal.custom_values),
                        deal.archived_at,
                        deal.updated_at,
                        deal.id,
                        deal.user_id,
                    ),
                )
                row = await cur.fetchone()
            await conn.commit()
        return _row_to_deal(row) if row is not None else None

    async def archive_deal(self, user_id: str, deal_id: str) -> Deal | None:
        """Arquiva (soft-delete); ``None`` se miss."""
        now = datetime.now(UTC)
        async with await psycopg.AsyncConnection.connect(self._conninfo) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    f"""
                    UPDATE crm_deals
                    SET archived_at = %s, updated_at = %s
                    WHERE id = %s AND user_id = %s
                    RETURNING {_DEAL_COLUMNS}
                    """,
                    (now, now, deal_id, user_id),
                )
                row = await cur.fetchone()
            await conn.commit()
        return _row_to_deal(row) if row is not None else None

    async def move_deal(
        self, user_id: str, deal_id: str, stage: DealStage
    ) -> Deal | None:
        """Atualiza só o estágio do deal; ``None`` se miss."""
        now = datetime.now(UTC)
        async with await psycopg.AsyncConnection.connect(self._conninfo) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    f"""
                    UPDATE crm_deals
                    SET stage = %s, updated_at = %s
                    WHERE id = %s AND user_id = %s
                    RETURNING {_DEAL_COLUMNS}
                    """,
                    (stage.value, now, deal_id, user_id),
                )
                row = await cur.fetchone()
            await conn.commit()
        return _row_to_deal(row) if row is not None else None

    # --- Leads -----------------------------------------------------------------

    async def create_lead(self, lead: Lead) -> Lead:
        """Insere lead e devolve a linha persistida."""
        async with await psycopg.AsyncConnection.connect(self._conninfo) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    f"""
                    INSERT INTO crm_leads ({_LEAD_COLUMNS})
                    VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s::jsonb, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    RETURNING {_LEAD_COLUMNS}
                    """,
                    (
                        lead.id,
                        lead.user_id,
                        lead.name,
                        lead.email,
                        lead.phone,
                        lead.company_name,
                        lead.interest,
                        lead.estimated_value,
                        lead.currency,
                        lead.qualification_score,
                        lead.notes,
                        lead.status.value,
                        lead.tags,
                        _as_jsonb(lead.custom_values),
                        lead.source.value if lead.source is not None else None,
                        lead.converted_at,
                        lead.converted_contact_id,
                        lead.converted_company_id,
                        lead.converted_deal_id,
                        lead.archived_at,
                        lead.created_at,
                        lead.updated_at,
                    ),
                )
                row = await cur.fetchone()
            await conn.commit()
        assert row is not None
        return _row_to_lead(row)

    async def list_leads(
        self, user_id: str, *, converted: bool = False
    ) -> list[Lead]:
        """Lista leads do user não-arquivados; `converted` alterna ativos/convertidos."""
        clauses = ["user_id = %s", "archived_at IS NULL"]
        params: list[object] = [user_id]
        if converted:
            clauses.append("converted_at IS NOT NULL")
        else:
            clauses.append("converted_at IS NULL")
        where = " AND ".join(clauses)
        async with await psycopg.AsyncConnection.connect(self._conninfo) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    f"SELECT {_LEAD_COLUMNS} FROM crm_leads "
                    f"WHERE {where} ORDER BY created_at DESC",
                    params,
                )
                rows = await cur.fetchall()
        return [_row_to_lead(r) for r in rows]

    async def get_lead(self, user_id: str, lead_id: str) -> Lead | None:
        """Retorna lead do user ou ``None``."""
        async with await psycopg.AsyncConnection.connect(self._conninfo) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    f"SELECT {_LEAD_COLUMNS} FROM crm_leads "
                    "WHERE id = %s AND user_id = %s",
                    (lead_id, user_id),
                )
                row = await cur.fetchone()
        return _row_to_lead(row) if row is not None else None

    async def convert_lead(self, lead: Lead) -> LeadConversionResult:
        """Cria Contato + Empresa (opcional) + Deal e marca o lead convertido.

        Tudo numa única conexão/transação — rollback explícito se qualquer
        INSERT/UPDATE falhar, sem deixar registros parciais no banco.
        """
        now = datetime.now(UTC)
        async with await psycopg.AsyncConnection.connect(self._conninfo) as conn:
            try:
                async with conn.cursor() as cur:
                    company: Company | None = None
                    if lead.company_name:
                        await cur.execute(
                            f"SELECT {_COMPANY_COLUMNS} FROM crm_companies "
                            "WHERE user_id = %s AND archived_at IS NULL "
                            "AND LOWER(name) = LOWER(%s) LIMIT 1",
                            (lead.user_id, lead.company_name),
                        )
                        existing_company_row = await cur.fetchone()
                        if existing_company_row is not None:
                            company = _row_to_company(existing_company_row)
                        else:
                            await cur.execute(
                                f"""
                                INSERT INTO crm_companies ({_COMPANY_COLUMNS})
                                VALUES (
                                    %s, %s, %s, %s, %s, %s, %s, %s, %s,
                                    %s::jsonb, %s, %s, %s, %s
                                )
                                RETURNING {_COMPANY_COLUMNS}
                                """,
                                (
                                    str(uuid.uuid4()),
                                    lead.user_id,
                                    lead.company_name,
                                    None,
                                    None,
                                    None,
                                    None,
                                    None,
                                    None,
                                    _as_jsonb({}),
                                    lead.id,
                                    None,
                                    now,
                                    now,
                                ),
                            )
                            company = _row_to_company(await cur.fetchone())

                    await cur.execute(
                        f"""
                        INSERT INTO crm_contacts ({_CONTACT_COLUMNS})
                        VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                            %s::jsonb, %s, %s, %s, %s
                        )
                        RETURNING {_CONTACT_COLUMNS}
                        """,
                        (
                            str(uuid.uuid4()),
                            lead.user_id,
                            lead.name,
                            lead.email,
                            lead.phone,
                            company.id if company is not None else None,
                            None,
                            [],
                            None,
                            None,
                            _as_jsonb({}),
                            lead.id,
                            None,
                            now,
                            now,
                        ),
                    )
                    contact = _row_to_contact(await cur.fetchone())

                    await cur.execute(
                        f"""
                        INSERT INTO crm_deals ({_DEAL_COLUMNS})
                        VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s
                        )
                        RETURNING {_DEAL_COLUMNS}
                        """,
                        (
                            str(uuid.uuid4()),
                            lead.user_id,
                            lead.name,
                            DealStage.QUALIFIED.value,
                            lead.estimated_value,
                            lead.currency,
                            contact.id,
                            company.id if company is not None else None,
                            _as_jsonb({}),
                            lead.id,
                            None,
                            now,
                            now,
                        ),
                    )
                    deal = _row_to_deal(await cur.fetchone())

                    await cur.execute(
                        f"""
                        UPDATE crm_leads SET
                            converted_at = %s, converted_contact_id = %s,
                            converted_company_id = %s, converted_deal_id = %s,
                            updated_at = %s
                        WHERE id = %s AND user_id = %s
                        RETURNING {_LEAD_COLUMNS}
                        """,
                        (
                            now,
                            contact.id,
                            company.id if company is not None else None,
                            deal.id,
                            now,
                            lead.id,
                            lead.user_id,
                        ),
                    )
                    updated_lead_row = await cur.fetchone()
                await conn.commit()
            except Exception:
                await conn.rollback()
                raise
        assert updated_lead_row is not None
        return LeadConversionResult(
            lead=_row_to_lead(updated_lead_row),
            contact=contact,
            company=company,
            deal=deal,
        )

    # --- Notes ---------------------------------------------------------------

    async def create_note(self, note: Note) -> Note:
        """Insere nota imutável e devolve a linha persistida."""
        async with await psycopg.AsyncConnection.connect(self._conninfo) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    f"""
                    INSERT INTO crm_notes ({_NOTE_COLUMNS})
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING {_NOTE_COLUMNS}
                    """,
                    (
                        note.id,
                        note.user_id,
                        note.body,
                        note.source.value,
                        note.contact_id,
                        note.company_id,
                        note.deal_id,
                        note.archived_at,
                        note.created_at,
                    ),
                )
                row = await cur.fetchone()
            await conn.commit()
        assert row is not None
        return _row_to_note(row)

    async def list_notes_for_contact(
        self,
        user_id: str,
        contact_id: str,
        *,
        include_archived: bool = False,
    ) -> list[Note]:
        """Notas do contato, mais recente primeiro."""
        return await self._list_notes(
            user_id, "contact_id", contact_id, include_archived=include_archived
        )

    async def list_notes_for_company(
        self,
        user_id: str,
        company_id: str,
        *,
        include_archived: bool = False,
    ) -> list[Note]:
        """Notas da empresa, mais recente primeiro."""
        return await self._list_notes(
            user_id, "company_id", company_id, include_archived=include_archived
        )

    async def list_notes_for_deal(
        self,
        user_id: str,
        deal_id: str,
        *,
        include_archived: bool = False,
    ) -> list[Note]:
        """Notas do deal, mais recente primeiro."""
        return await self._list_notes(
            user_id, "deal_id", deal_id, include_archived=include_archived
        )

    async def _list_notes(
        self,
        user_id: str,
        target_column: str,
        target_id: str,
        *,
        include_archived: bool,
    ) -> list[Note]:
        if target_column not in {"contact_id", "company_id", "deal_id"}:
            raise ValueError(f"coluna de alvo inválida: {target_column}")
        clauses = ["user_id = %s", f"{target_column} = %s"]
        params: list[object] = [user_id, target_id]
        if not include_archived:
            clauses.append("archived_at IS NULL")
        where = " AND ".join(clauses)
        async with await psycopg.AsyncConnection.connect(self._conninfo) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    f"SELECT {_NOTE_COLUMNS} FROM crm_notes "
                    f"WHERE {where} ORDER BY created_at DESC",
                    params,
                )
                rows = await cur.fetchall()
        return [_row_to_note(r) for r in rows]

    # --- Field definitions ---------------------------------------------------

    async def create_field_definition(
        self, definition: FieldDefinition
    ) -> FieldDefinition:
        """Insere definição; duplicata → DuplicateFieldDefinitionError."""
        async with await psycopg.AsyncConnection.connect(self._conninfo) as conn:
            async with conn.cursor() as cur:
                try:
                    await cur.execute(
                        f"""
                        INSERT INTO crm_field_definitions ({_FIELD_DEF_COLUMNS})
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING {_FIELD_DEF_COLUMNS}
                        """,
                        (
                            definition.id,
                            definition.user_id,
                            definition.entity.value,
                            definition.key,
                            definition.label,
                            definition.field_type.value,
                            definition.created_at,
                            definition.updated_at,
                        ),
                    )
                except UniqueViolation as exc:
                    await conn.rollback()
                    raise DuplicateFieldDefinitionError(
                        f"field definition already exists: "
                        f"{definition.entity.value}/{definition.key}"
                    ) from exc
                row = await cur.fetchone()
            await conn.commit()
        assert row is not None
        return _row_to_field_definition(row)

    async def list_field_definitions(
        self,
        user_id: str,
        *,
        entity: FieldEntity | None = None,
    ) -> list[FieldDefinition]:
        """Lista definições do user; filtro opcional por entidade."""
        clauses = ["user_id = %s"]
        params: list[object] = [user_id]
        if entity is not None:
            clauses.append("entity = %s")
            params.append(entity.value)
        where = " AND ".join(clauses)
        async with await psycopg.AsyncConnection.connect(self._conninfo) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    f"SELECT {_FIELD_DEF_COLUMNS} FROM crm_field_definitions "
                    f"WHERE {where} ORDER BY key ASC",
                    params,
                )
                rows = await cur.fetchall()
        return [_row_to_field_definition(r) for r in rows]

    async def update_field_definition_label(
        self, user_id: str, definition_id: str, label: str
    ) -> FieldDefinition | None:
        """Atualiza só o label; ``None`` se miss/cross-user."""
        now = datetime.now(UTC)
        async with await psycopg.AsyncConnection.connect(self._conninfo) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    f"""
                    UPDATE crm_field_definitions
                    SET label = %s, updated_at = %s
                    WHERE id = %s AND user_id = %s
                    RETURNING {_FIELD_DEF_COLUMNS}
                    """,
                    (label, now, definition_id, user_id),
                )
                row = await cur.fetchone()
            await conn.commit()
        return _row_to_field_definition(row) if row is not None else None
