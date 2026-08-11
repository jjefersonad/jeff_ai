"""Adapter Postgres de `EmailAccountRepositoryPort`.

Todas as queries filtram por `user_id`. Miss cross-user → `None`/`False`
(nunca exceção) — mesmo padrão de `PostgresCrmRepository`. Padrão de
acesso a banco: `psycopg` assíncrono, uma conexão por operação.
"""
from __future__ import annotations

from typing import Any

import psycopg

from src.application.ports.email_account_repository import (
    EmailAccountRepositoryPort,
)
from src.domain.email import EmailAccount, EmailAccountStatus

_COLUMNS = (
    "id, user_id, user_integration_id, provider, display_name, status, "
    "last_synced_at, is_active, created_at, updated_at"
)


def _row_to_account(row: tuple[Any, ...]) -> EmailAccount:
    (
        account_id,
        user_id,
        user_integration_id,
        provider,
        display_name,
        status,
        last_synced_at,
        is_active,
        created_at,
        updated_at,
    ) = row
    return EmailAccount(
        id=str(account_id),
        user_id=str(user_id),
        user_integration_id=str(user_integration_id),
        provider=provider,
        display_name=display_name,
        status=EmailAccountStatus(status),
        last_synced_at=last_synced_at,
        is_active=is_active,
        created_at=created_at,
        updated_at=updated_at,
    )


class PostgresEmailAccountRepository(EmailAccountRepositoryPort):
    """Persiste `EmailAccount` na tabela `email_accounts`, escopada a `user_id`."""

    def __init__(self, conninfo: str) -> None:
        """Guarda o conninfo Postgres — uma conexão é aberta por operação."""
        self._conninfo = conninfo

    async def create(self, account: EmailAccount) -> EmailAccount:
        """Insere a conta e devolve a linha persistida."""
        async with await psycopg.AsyncConnection.connect(self._conninfo) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    f"""
                    INSERT INTO email_accounts ({_COLUMNS})
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING {_COLUMNS}
                    """,
                    (
                        account.id,
                        account.user_id,
                        account.user_integration_id,
                        account.provider,
                        account.display_name,
                        account.status.value,
                        account.last_synced_at,
                        account.is_active,
                        account.created_at,
                        account.updated_at,
                    ),
                )
                row = await cur.fetchone()
            await conn.commit()
        assert row is not None
        return _row_to_account(row)

    async def get(self, user_id: str, account_id: str) -> EmailAccount | None:
        """Retorna a conta do `user_id` ou `None` (miss ou cross-user)."""
        async with await psycopg.AsyncConnection.connect(self._conninfo) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    f"SELECT {_COLUMNS} FROM email_accounts "
                    "WHERE id = %s AND user_id = %s",
                    (account_id, user_id),
                )
                row = await cur.fetchone()
        return _row_to_account(row) if row is not None else None

    async def list_by_user(self, user_id: str) -> list[EmailAccount]:
        """Retorna as contas do `user_id`, ordenadas por criação."""
        async with await psycopg.AsyncConnection.connect(self._conninfo) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    f"SELECT {_COLUMNS} FROM email_accounts "
                    "WHERE user_id = %s ORDER BY created_at",
                    (user_id,),
                )
                rows = await cur.fetchall()
        return [_row_to_account(r) for r in rows]

    async def list_all(self) -> list[EmailAccount]:
        """Retorna TODAS as contas, de todos os usuários (uso do sync worker)."""
        async with await psycopg.AsyncConnection.connect(self._conninfo) as conn:
            async with conn.cursor() as cur:
                await cur.execute(f"SELECT {_COLUMNS} FROM email_accounts ORDER BY created_at")
                rows = await cur.fetchall()
        return [_row_to_account(r) for r in rows]

    async def update(self, account: EmailAccount) -> EmailAccount | None:
        """Atualiza a conta própria; `None` se miss ou cross-user."""
        async with await psycopg.AsyncConnection.connect(self._conninfo) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    f"""
                    UPDATE email_accounts SET
                        display_name = %s, status = %s, last_synced_at = %s,
                        is_active = %s, updated_at = %s
                    WHERE id = %s AND user_id = %s
                    RETURNING {_COLUMNS}
                    """,
                    (
                        account.display_name,
                        account.status.value,
                        account.last_synced_at,
                        account.is_active,
                        account.updated_at,
                        account.id,
                        account.user_id,
                    ),
                )
                row = await cur.fetchone()
            await conn.commit()
        return _row_to_account(row) if row is not None else None

    async def delete(self, user_id: str, account_id: str) -> bool:
        """Remove a conta própria; `True` se removida, `False` se miss/cross-user."""
        async with await psycopg.AsyncConnection.connect(self._conninfo) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "DELETE FROM email_accounts WHERE id = %s AND user_id = %s",
                    (account_id, user_id),
                )
                deleted = cur.rowcount > 0
            await conn.commit()
        return deleted
