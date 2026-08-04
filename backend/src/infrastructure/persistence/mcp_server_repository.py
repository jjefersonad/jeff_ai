"""Adapter Postgres de `McpServerRepositoryPort` (task
`user-scoped-mcp-config-storage-task-store-2`).

Cifra/decifra os valores de `env`/`headers` (REQ-002 do spec
`user-mcp-server-store`) reusando `credentials_crypto.py` *verbatim* — mesmo
helper, mesma chave (`INTEGRATION_CREDENTIALS_KEY`), mesmo envelope por valor
`{"__enc__": ciphertext}` que `user_integrations_repository.py` já usa,
incluindo os dois comportamentos corrigidos ali em produção (2026-08-03):
sempre `json.dumps` o valor antes de cifrar (evita ambiguidade de tipo em
strings puramente numéricas) e pular uma linha undecryptável (chave
rotacionada/perdida) em vez de derrubar a listagem inteira.

Padrão de acesso a banco: `psycopg` assíncrono, uma conexão por operação,
mesmo de `user_integrations_repository.py`.
"""
from __future__ import annotations

import json
import logging
from typing import Any

import psycopg

from src.application.ports.mcp_server_repository import McpServerRepositoryPort
from src.domain.mcp import McpServerConfig
from src.infrastructure.persistence.credentials_crypto import decrypt, encrypt

logger = logging.getLogger(__name__)

_COLUMNS = (
    "id, user_id, name, transport, command, args, url, env, headers, "
    "created_at, updated_at"
)

_UPSERT = f"""
INSERT INTO user_mcp_servers ({_COLUMNS})
VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s::jsonb, %s::jsonb, %s, %s)
ON CONFLICT (user_id, name) DO UPDATE SET
    transport = EXCLUDED.transport,
    command = EXCLUDED.command,
    args = EXCLUDED.args,
    url = EXCLUDED.url,
    env = EXCLUDED.env,
    headers = EXCLUDED.headers,
    updated_at = EXCLUDED.updated_at
"""

_SELECT_BY_USER_AND_NAME = (
    f"SELECT {_COLUMNS} FROM user_mcp_servers WHERE user_id = %s AND name = %s"
)
_SELECT_BY_USER = (
    f"SELECT {_COLUMNS} FROM user_mcp_servers WHERE user_id = %s ORDER BY created_at"
)
_SELECT_ALL = f"SELECT {_COLUMNS} FROM user_mcp_servers ORDER BY created_at"
_DELETE = "DELETE FROM user_mcp_servers WHERE user_id = %s AND name = %s"

_ENVELOPE_KEY = "__enc__"


def _encrypt_values(values: dict[str, str]) -> dict[str, object]:
    """Cifra cada valor de `env`/`headers`, embrulhando em `{__enc__: ct}`.

    SEMPRE serializa o valor via `json.dumps` antes de cifrar, mesma
    disciplina de `user_integrations_repository._encrypt_config` — evita que
    uma string puramente numérica volte como `int` na decifragem.
    """
    return {key: {_ENVELOPE_KEY: encrypt(json.dumps(value))} for key, value in values.items()}


def _decrypt_values(values: dict[str, object] | None) -> dict[str, str]:
    """Inverso de `_encrypt_values`. `None` (coluna vazia) vira `{}`."""
    decrypted: dict[str, str] = {}
    for key, value in (values or {}).items():
        if isinstance(value, dict) and _ENVELOPE_KEY in value:
            ciphertext = value[_ENVELOPE_KEY]
            if not isinstance(ciphertext, str):
                continue
            plaintext = decrypt(ciphertext)
            decrypted[key] = json.loads(plaintext)
        else:
            decrypted[key] = value
    return decrypted


def _row_to_server(row: tuple[Any, ...]) -> McpServerConfig:
    (
        server_id,
        user_id,
        name,
        transport,
        command,
        args,
        url,
        env,
        headers,
        created_at,
        updated_at,
    ) = row
    return McpServerConfig(
        id=str(server_id),
        user_id=str(user_id),
        name=name,
        transport=transport,
        command=command,
        args=list(args or []),
        url=url,
        env=_decrypt_values(env),
        headers=_decrypt_values(headers),
        created_at=created_at,
        updated_at=updated_at,
    )


def _rows_to_servers_skipping_undecryptable(
    rows: list[tuple[Any, ...]],
) -> list[McpServerConfig]:
    """Decifra cada linha; uma linha cujo `env`/`headers` não decifra com a
    chave ATIVA (`INTEGRATION_CREDENTIALS_KEY` rotacionada/perdida) é logada e
    pulada, em vez de derrubar a leitura das demais linhas — mesmo raciocínio
    de `user_integrations_repository._rows_to_integrations_skipping_undecryptable`.
    """
    servers: list[McpServerConfig] = []
    for row in rows:
        try:
            servers.append(_row_to_server(row))
        except ValueError:
            server_id = row[0]
            logger.warning(
                "user_mcp_servers id=%s não pôde ser decifrado com a chave "
                "ativa — pulado (não derruba as demais linhas).",
                server_id,
            )
    return servers


class PostgresMcpServerRepository(McpServerRepositoryPort):
    """Persiste `McpServerConfig` na tabela `user_mcp_servers` com cifra em `env`/`headers`."""

    def __init__(self, conninfo: str) -> None:
        """Guarda o conninfo Postgres — uma conexão é aberta por operação."""
        self._conninfo = conninfo

    async def save(self, server: McpServerConfig) -> None:
        """Upsert por `(user_id, name)`: cifra `env`/`headers` e persiste (REQ-001/REQ-002)."""
        encrypted_env = _encrypt_values(server.env)
        encrypted_headers = _encrypt_values(server.headers)
        async with await psycopg.AsyncConnection.connect(self._conninfo) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    _UPSERT,
                    (
                        server.id,
                        server.user_id,
                        server.name,
                        server.transport,
                        server.command,
                        json.dumps(server.args),
                        server.url,
                        json.dumps(encrypted_env),
                        json.dumps(encrypted_headers),
                        server.created_at,
                        server.updated_at,
                    ),
                )
            await conn.commit()

    async def get(self, user_id: str, name: str) -> McpServerConfig | None:
        """Retorna o servidor decifrado ou `None` (nunca exceção) para `(user_id, name)` inexistente."""
        async with await psycopg.AsyncConnection.connect(self._conninfo) as conn:
            async with conn.cursor() as cur:
                await cur.execute(_SELECT_BY_USER_AND_NAME, (user_id, name))
                row = await cur.fetchone()
        return _row_to_server(row) if row is not None else None

    async def list_by_user(self, user_id: str) -> list[McpServerConfig]:
        """Retorna os servidores do `user_id`, decifrados (REQ-001).

        Uma linha undecryptável com a chave ativa é pulada (logada), em vez
        de derrubar a listagem inteira do usuário.
        """
        async with await psycopg.AsyncConnection.connect(self._conninfo) as conn:
            async with conn.cursor() as cur:
                await cur.execute(_SELECT_BY_USER, (user_id,))
                rows = await cur.fetchall()
        return _rows_to_servers_skipping_undecryptable(rows)

    async def list_all(self) -> list[McpServerConfig]:
        """Retorna TODOS os servidores, de todos os usuários (uso restrito a `role=admin`).

        A checagem `role=admin` é responsabilidade do use case chamador. Uma
        linha undecryptável com a chave ativa é pulada (logada) — ver
        `_rows_to_servers_skipping_undecryptable`.
        """
        async with await psycopg.AsyncConnection.connect(self._conninfo) as conn:
            async with conn.cursor() as cur:
                await cur.execute(_SELECT_ALL)
                rows = await cur.fetchall()
        return _rows_to_servers_skipping_undecryptable(rows)

    async def delete(self, user_id: str, name: str) -> None:
        """Remove o servidor; tolerante a `(user_id, name)` inexistente (no-op)."""
        async with await psycopg.AsyncConnection.connect(self._conninfo) as conn:
            async with conn.cursor() as cur:
                await cur.execute(_DELETE, (user_id, name))
            await conn.commit()
