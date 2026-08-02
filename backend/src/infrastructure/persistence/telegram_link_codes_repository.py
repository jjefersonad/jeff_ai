"""Adapter Postgres de `TelegramLinkCodeRepositoryPort`.

Persiste em `telegram_link_codes` (schema criado por
`telegram_link_codes_schema.py`, task `user-integration-credentials-task-db-2`).
Mesmo padrão de conexão-por-operação de `user_integrations_repository.py`.
`get()` retorna `None` tanto para código nunca emitido quanto para código já
`delete()`-ado (invalidação single-use é uma remoção de linha, não uma flag —
task `user-integration-credentials-task-linking-1`).
"""
from __future__ import annotations

from typing import Any

import psycopg

from src.application.ports.telegram_link_code_repository import (
    TelegramLinkCodeRepositoryPort,
)
from src.domain.integrations import TelegramLinkCode

_COLUMNS = "code, user_id, expires_at"

_INSERT = f"""
INSERT INTO telegram_link_codes ({_COLUMNS})
VALUES (%s, %s, %s)
"""

_SELECT_BY_CODE = f"SELECT {_COLUMNS} FROM telegram_link_codes WHERE code = %s"
_DELETE = "DELETE FROM telegram_link_codes WHERE code = %s"


def _row_to_link_code(row: tuple[Any, ...]) -> TelegramLinkCode:
    code, user_id, expires_at = row
    return TelegramLinkCode(code=code, user_id=str(user_id), expires_at=expires_at)


class PostgresTelegramLinkCodeRepository(TelegramLinkCodeRepositoryPort):
    """Persiste `TelegramLinkCode` na tabela `telegram_link_codes`."""

    def __init__(self, conninfo: str) -> None:
        """Guarda o conninfo Postgres — uma conexão é aberta por operação."""
        self._conninfo = conninfo

    async def save(self, link_code: TelegramLinkCode) -> None:
        """Insere o código (chave primária `code`, gerada nova a cada chamada)."""
        async with await psycopg.AsyncConnection.connect(self._conninfo) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    _INSERT,
                    (link_code.code, link_code.user_id, link_code.expires_at),
                )
            await conn.commit()

    async def get(self, code: str) -> TelegramLinkCode | None:
        """Retorna o código pelo valor, ou `None` se inexistente/já invalidado."""
        async with await psycopg.AsyncConnection.connect(self._conninfo) as conn:
            async with conn.cursor() as cur:
                await cur.execute(_SELECT_BY_CODE, (code,))
                row = await cur.fetchone()
        return _row_to_link_code(row) if row is not None else None

    async def delete(self, code: str) -> None:
        """Remove o código; tolerante a código inexistente (no-op)."""
        async with await psycopg.AsyncConnection.connect(self._conninfo) as conn:
            async with conn.cursor() as cur:
                await cur.execute(_DELETE, (code,))
            await conn.commit()
