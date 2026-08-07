"""Adapter Postgres de `CrmRepositoryPort` (add-simple-crm-module-task-persistence-1).

Todas as queries filtram por `user_id`. Miss cross-user → `None` / lista vazia.
Padrão: `psycopg` async, uma conexão por operação (como
`user_integrations_repository` / `scheduled_task_repository`).
"""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import psycopg

from src.application.ports.crm_repository import CrmRepositoryPort
from src.domain.crm import Company, Contact, Deal, DealStage, Note, NoteSource

_CONTACT_COLUMNS = (
    "id, user_id, name, email, phone, company_id, status, tags, "
    "archived_at, created_at, updated_at"
)
_COMPANY_COLUMNS = (
    "id, user_id, name, website, domain, phone, notes, "
    "archived_at, created_at, updated_at"
)
_DEAL_COLUMNS = (
    "id, user_id, title, stage, value, currency, contact_id, company_id, "
    "archived_at, created_at, updated_at"
)
_NOTE_COLUMNS = (
    "id, user_id, body, source, contact_id, company_id, deal_id, created_at"
)


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
        created_at=created_at,
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
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                        notes = %s, archived_at = %s, updated_at = %s
                    WHERE id = %s AND user_id = %s
                    RETURNING {_COMPANY_COLUMNS}
                    """,
                    (
                        company.name,
                        company.website,
                        company.domain,
                        company.phone,
                        company.notes,
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
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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

    async def list_contacts(
        self,
        user_id: str,
        *,
        query: str | None = None,
        company_id: str | None = None,
        include_archived: bool = False,
    ) -> list[Contact]:
        """Lista contatos do user; filtro opcional por termo/empresa."""
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
        where = " AND ".join(clauses)
        async with await psycopg.AsyncConnection.connect(self._conninfo) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    f"SELECT {_CONTACT_COLUMNS} FROM crm_contacts "
                    f"WHERE {where} ORDER BY created_at DESC",
                    params,
                )
                rows = await cur.fetchall()
        return [_row_to_contact(r) for r in rows]

    async def update_contact(self, contact: Contact) -> Contact | None:
        """Atualiza contato próprio; ``None`` se miss."""
        async with await psycopg.AsyncConnection.connect(self._conninfo) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    f"""
                    UPDATE crm_contacts SET
                        name = %s, email = %s, phone = %s, company_id = %s,
                        status = %s, tags = %s, archived_at = %s, updated_at = %s
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
        """Arquiva (soft-delete); ``None`` se miss."""
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
            await conn.commit()
        return _row_to_contact(row) if row is not None else None

    # --- Deals ---------------------------------------------------------------

    async def create_deal(self, deal: Deal) -> Deal:
        """Insere deal e devolve a linha persistida."""
        async with await psycopg.AsyncConnection.connect(self._conninfo) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    f"""
                    INSERT INTO crm_deals ({_DEAL_COLUMNS})
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                        contact_id = %s, company_id = %s, archived_at = %s,
                        updated_at = %s
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

    # --- Notes ---------------------------------------------------------------

    async def create_note(self, note: Note) -> Note:
        """Insere nota imutável e devolve a linha persistida."""
        async with await psycopg.AsyncConnection.connect(self._conninfo) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    f"""
                    INSERT INTO crm_notes ({_NOTE_COLUMNS})
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
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
                        note.created_at,
                    ),
                )
                row = await cur.fetchone()
            await conn.commit()
        assert row is not None
        return _row_to_note(row)

    async def list_notes_for_contact(
        self, user_id: str, contact_id: str
    ) -> list[Note]:
        """Notas do contato, mais recente primeiro."""
        return await self._list_notes(user_id, "contact_id", contact_id)

    async def list_notes_for_company(
        self, user_id: str, company_id: str
    ) -> list[Note]:
        """Notas da empresa, mais recente primeiro."""
        return await self._list_notes(user_id, "company_id", company_id)

    async def list_notes_for_deal(self, user_id: str, deal_id: str) -> list[Note]:
        """Notas do deal, mais recente primeiro."""
        return await self._list_notes(user_id, "deal_id", deal_id)

    async def _list_notes(
        self, user_id: str, target_column: str, target_id: str
    ) -> list[Note]:
        if target_column not in {"contact_id", "company_id", "deal_id"}:
            raise ValueError(f"coluna de alvo inválida: {target_column}")
        async with await psycopg.AsyncConnection.connect(self._conninfo) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    f"SELECT {_NOTE_COLUMNS} FROM crm_notes "
                    f"WHERE user_id = %s AND {target_column} = %s "
                    "ORDER BY created_at DESC",
                    (user_id, target_id),
                )
                rows = await cur.fetchall()
        return [_row_to_note(r) for r in rows]
