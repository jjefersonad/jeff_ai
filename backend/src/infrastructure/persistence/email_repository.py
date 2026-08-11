"""Adapter Postgres de `EmailRepositoryPort`.

Todas as queries filtram por `user_id` via subquery em `email_accounts`.
Miss cross-user → `None`/`False` (nunca exceção). Padrão de acesso a banco:
`psycopg` assíncrono, uma conexão por operação.
"""
from __future__ import annotations

import json
from typing import Any

import psycopg

from src.application.ports.email_repository import EmailRepositoryPort
from src.domain.email import Email, ParsedAttachment, ParsedMessage

_COLUMNS = (
    "id, email_account_id, message_id, thread_id, folder, "
    "from_address, from_name, to_addresses, cc_addresses, bcc_addresses, "
    "subject, body_html, body_text, is_read, is_starred, has_attachments, "
    "contact_id, received_at, created_at"
)

#: Mesmas colunas, qualificadas com o alias `e.` — necessário nas queries com
#: JOIN em `email_accounts`, cuja própria coluna `id` colide com `emails.id`
#: se as colunas não forem qualificadas (`AmbiguousColumn`).
_SELECT_COLUMNS = ", ".join(f"e.{name.strip()}" for name in _COLUMNS.split(","))

#: Fragment SQL reutilizável para o JOIN que verifica ownership.
_OWNERSHIP_JOIN = (
    "JOIN email_accounts ea ON ea.id = e.email_account_id "
    "WHERE ea.user_id = %s"
)


def _row_to_email(row: tuple[Any, ...]) -> Email:
    (
        id_,
        email_account_id,
        message_id,
        thread_id,
        folder,
        from_address,
        from_name,
        to_addresses,
        cc_addresses,
        bcc_addresses,
        subject,
        body_html,
        body_text,
        is_read,
        is_starred,
        has_attachments,
        contact_id,
        received_at,
        created_at,
    ) = row
    return Email(
        id=str(id_),
        email_account_id=str(email_account_id),
        message_id=str(message_id),
        thread_id=str(thread_id) if thread_id is not None else None,
        folder=folder,
        from_address=str(from_address),
        from_name=str(from_name) if from_name is not None else None,
        to_addresses=to_addresses if isinstance(to_addresses, list) else [],
        cc_addresses=cc_addresses if isinstance(cc_addresses, list) else [],
        bcc_addresses=bcc_addresses if isinstance(bcc_addresses, list) else [],
        subject=str(subject) if subject is not None else None,
        body_html=str(body_html) if body_html is not None else None,
        body_text=str(body_text) if body_text is not None else None,
        is_read=bool(is_read),
        is_starred=bool(is_starred),
        has_attachments=bool(has_attachments),
        contact_id=str(contact_id) if contact_id is not None else None,
        received_at=received_at,
        created_at=created_at,
    )


class PostgresEmailRepository(EmailRepositoryPort):
    """Persiste `Email` na tabela `emails`, escopada a `user_id` via JOIN."""

    def __init__(self, conninfo: str) -> None:
        """Guarda o conninfo Postgres — uma conexão é aberta por operação."""
        self._conninfo = conninfo

    async def upsert_email(
        self,
        email_account_id: str,
        message: ParsedMessage,
        attachments: list[ParsedAttachment] | None = None,
        contact_id: str | None = None,
    ) -> Email:
        """Insere/atualiza por `(email_account_id, message_id)`; substitui os anexos.

        `contact_id` associa a mensagem a um `crm_contacts` (REQ-006). No
        `INSERT`, persiste o valor recebido. No `ON CONFLICT` (re-ingest da
        mesma mensagem), preserva um link pré-existente: `contact_id =
        COALESCE(EXCLUDED.contact_id, emails.contact_id)` — uma re-sincronia
        sem novo match de contato não deve desassociar mensagens já linkadas.
        """
        attachments = attachments or []
        async with await psycopg.AsyncConnection.connect(self._conninfo) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    f"""
                    INSERT INTO emails (
                        email_account_id, message_id, folder, from_address,
                        from_name, to_addresses, subject, body_html, body_text,
                        has_attachments, contact_id, received_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (email_account_id, message_id) DO UPDATE SET
                        folder = EXCLUDED.folder,
                        from_address = EXCLUDED.from_address,
                        from_name = EXCLUDED.from_name,
                        to_addresses = EXCLUDED.to_addresses,
                        subject = EXCLUDED.subject,
                        body_html = EXCLUDED.body_html,
                        body_text = EXCLUDED.body_text,
                        has_attachments = EXCLUDED.has_attachments,
                        contact_id = COALESCE(EXCLUDED.contact_id, emails.contact_id),
                        received_at = EXCLUDED.received_at
                    RETURNING {_COLUMNS}
                    """,
                    (
                        email_account_id,
                        message.message_id,
                        message.folder,
                        message.from_address,
                        message.from_name,
                        json.dumps(list(message.to_addresses)),
                        message.subject,
                        message.body_html,
                        message.body_text,
                        bool(attachments),
                        contact_id,
                        message.received_at,
                    ),
                )
                row = await cur.fetchone()
                email = _row_to_email(row)

                await cur.execute(
                    "DELETE FROM email_attachments WHERE email_id = %s", (email.id,)
                )
                for attachment in attachments:
                    await cur.execute(
                        """
                        INSERT INTO email_attachments
                            (email_id, filename, mime_type, size_bytes, storage_path)
                        VALUES (%s, %s, %s, %s, %s)
                        """,
                        (
                            email.id,
                            attachment.filename,
                            attachment.mime_type,
                            attachment.size_bytes,
                            attachment.storage_path,
                        ),
                    )
            await conn.commit()
        return email

    async def list_by_account(
        self,
        user_id: str,
        account_id: str | None = None,
        folder: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[Email]:
        """Retorna emails do user, ordenados por `received_at` DESC.

        Com `account_id`+`folder`, filtra por ambos; sem nenhum dos dois,
        retorna o inbox unificado do user (todas as contas/folders).

        O `folder` é comparado via `LOWER() = LOWER()` porque (a) o
        `imap_client` persiste com casing do servidor IMAP (`INBOX` é o
        padrão RFC, mas provedores variam), (b) o `send_email` persiste
        `Sent` (camel-case) e (c) o frontend (`InboxPanel`) usa
        `STANDARD_FOLDERS = ["Inbox", "Sent", ...]` (Title-Case).
        Comparação exata retornava 0 rows para qualquer uma dessas
        combinações — bug em produção 2026-08-10: emails sincronizados
        apareciam no DB mas não no frontend.
        """
        where_clauses = ["ea.user_id = %s"]
        params: list[Any] = [user_id]
        if account_id is not None:
            where_clauses.append("e.email_account_id = %s")
            params.append(account_id)
        if folder is not None:
            where_clauses.append("LOWER(e.folder) = LOWER(%s)")
            params.append(folder)
        params.extend([limit, offset])
        where_sql = " AND ".join(where_clauses)
        async with await psycopg.AsyncConnection.connect(self._conninfo) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    f"""
                    SELECT {_SELECT_COLUMNS}
                    FROM emails e
                    JOIN email_accounts ea ON ea.id = e.email_account_id
                    WHERE {where_sql}
                    ORDER BY e.received_at DESC
                    LIMIT %s OFFSET %s
                    """,
                    tuple(params),
                )
                rows = await cur.fetchall()
        return [_row_to_email(r) for r in rows]

    async def get(self, user_id: str, email_id: str) -> Email | None:
        """Retorna o email do `user_id` ou `None` (miss ou cross-user)."""
        async with await psycopg.AsyncConnection.connect(self._conninfo) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    f"""
                    SELECT {_SELECT_COLUMNS}
                    FROM emails e
                    {_OWNERSHIP_JOIN}
                    AND e.id = %s
                    """,
                    (user_id, email_id),
                )
                row = await cur.fetchone()
        return _row_to_email(row) if row is not None else None

    async def get_by_message_id(
        self, user_id: str, message_id: str
    ) -> Email | None:
        """Retorna o email do `user_id` cujo `message_id` (header IMAP) bate, ou `None`.

        Usado pelo `SendEmail.execute` (REQ-005 email-inbox) para resolver
        o `in_reply_to` recebido do frontend — o frontend envia o header
        `Message-ID:` IMAP (ex.: `CAE3...@mail.gmail.com`), não o UUID da
        linha, então `repo.get(user_id, message_id)` falhava com
        `psycopg.errors.InvalidTextRepresentation: invalid input syntax
        for type uuid` (bug em produção 2026-08-10). Filtra por `user_id`
        via JOIN em `email_accounts` para não vazar mensagens de outro
        user (mesma defesa de `get`).
        """
        async with await psycopg.AsyncConnection.connect(self._conninfo) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    f"""
                    SELECT {_SELECT_COLUMNS}
                    FROM emails e
                    {_OWNERSHIP_JOIN}
                    AND e.message_id = %s
                    """,
                    (user_id, message_id),
                )
                row = await cur.fetchone()
        return _row_to_email(row) if row is not None else None

    async def search(
        self,
        user_id: str,
        account_id: str | None,
        query: str,
        limit: int,
    ) -> list[Email]:
        """Busca por `query` em `subject`, `body_text` e `from_address` (ILIKE %query%)."""
        pattern = f"%{query}%"
        async with await psycopg.AsyncConnection.connect(self._conninfo) as conn:
            async with conn.cursor() as cur:
                if account_id is not None:
                    await cur.execute(
                        f"""
                        SELECT {_SELECT_COLUMNS}
                        FROM emails e
                        {_OWNERSHIP_JOIN}
                        AND e.email_account_id = %s
                        AND (
                            e.subject ILIKE %s
                            OR e.body_text ILIKE %s
                            OR e.from_address ILIKE %s
                        )
                        ORDER BY e.received_at DESC
                        LIMIT %s
                        """,
                        (user_id, account_id, pattern, pattern, pattern, limit),
                    )
                else:
                    await cur.execute(
                        f"""
                        SELECT {_SELECT_COLUMNS}
                        FROM emails e
                        {_OWNERSHIP_JOIN}
                        AND (
                            e.subject ILIKE %s
                            OR e.body_text ILIKE %s
                            OR e.from_address ILIKE %s
                        )
                        ORDER BY e.received_at DESC
                        LIMIT %s
                        """,
                        (user_id, pattern, pattern, pattern, limit),
                    )
                rows = await cur.fetchall()
        return [_row_to_email(r) for r in rows]

    async def mark_read(self, user_id: str, email_id: str) -> bool:
        """Marca email como lido; `True` se atualizado, `False` se miss/cross-user."""
        async with await psycopg.AsyncConnection.connect(self._conninfo) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    UPDATE emails e
                    SET is_read = true
                    FROM email_accounts ea
                    WHERE ea.id = e.email_account_id
                        AND ea.user_id = %s
                        AND e.id = %s
                    """,
                    (user_id, email_id),
                )
                updated = cur.rowcount > 0
            await conn.commit()
        return updated

    async def move_folder(self, user_id: str, email_id: str, folder: str) -> bool:
        """Move email para outra folder; `True` se movido, `False` se miss/cross-user."""
        async with await psycopg.AsyncConnection.connect(self._conninfo) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    UPDATE emails e
                    SET folder = %s
                    FROM email_accounts ea
                    WHERE ea.id = e.email_account_id
                        AND ea.user_id = %s
                        AND e.id = %s
                    """,
                    (folder, user_id, email_id),
                )
                updated = cur.rowcount > 0
            await conn.commit()
        return updated
