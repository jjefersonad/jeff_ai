"""CRUD de servidores MCP por usuário — delega a `McpServerRepositoryPort`.

Reescrito pela task `user-scoped-mcp-config-storage-task-store-3` (REQ-001 do
spec `user-mcp-server-store`): não lê/escreve mais `mcp_servers.json` — cada
função abaixo recebe `user_id` como primeiro parâmetro e só enxerga as linhas
desse usuário (`repo.get`/`repo.list_by_user`), delegando a persistência (e a
cifra de `env`/`headers`, REQ-002) a `PostgresMcpServerRepository`. Cobrir
"role=admin vê todos" é responsabilidade do caller — use `repo.list_all()`
diretamente (ver `mcp_admin_api.py`, task `admin-2`), este módulo não expõe
isso.

Continua consumido só por `mcp_admin_api.py` (ver
`test_mcp_admin_import_boundary.py`) — o agente não tem alcance de código até
aqui.

## Sobre `env`/`headers`

Diferente da versão anterior baseada em arquivo, os valores aqui são reais
(cifrados em repouso pelo repositório, nunca `${VAR}`) — a convenção REQ-007
de referência a variável de ambiente era específica do armazenamento em
arquivo texto puro e não se aplica mais neste caminho (ver design Decision
2 de `user-scoped-mcp-config-storage`). `mcp_client.build_connection`
continua compatível: sua resolução de `${VAR}` é um no-op para qualquer
valor que não bata esse padrão exato.
"""
from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime
from typing import Any

from src.application.ports.mcp_server_repository import McpServerRepositoryPort
from src.domain.mcp import McpServerConfig
from src.infrastructure.persistence.mcp_server_repository import (
    PostgresMcpServerRepository,
)


class McpServerConfigError(ValueError):
    """Operação de CRUD inválida (nome já usado pelo mesmo usuário, servidor inexistente)."""


def _default_repository() -> McpServerRepositoryPort:
    """Constrói o repositório a partir de `POSTGRES_URI`.

    Mesmo padrão de `integrations_router._user_integration_repository()`.
    """
    return PostgresMcpServerRepository(os.environ["POSTGRES_URI"])


def _to_entry(server: McpServerConfig) -> dict[str, Any]:
    """Forma exposta ao caller — mesmas chaves que `mcp_client.build_connection` espera."""
    return {
        "transport": server.transport,
        "command": server.command,
        "args": list(server.args),
        "url": server.url,
        "env": dict(server.env),
        "headers": dict(server.headers),
    }


async def list_servers(
    user_id: str, *, repository: McpServerRepositoryPort | None = None
) -> dict[str, dict[str, Any]]:
    """Devolve as entradas de `user_id`, chaveadas por nome (REQ-001)."""
    repo = repository or _default_repository()
    servers = await repo.list_by_user(user_id)
    return {server.name: _to_entry(server) for server in servers}


async def list_all_servers(
    *, repository: McpServerRepositoryPort | None = None
) -> list[McpServerConfig]:
    """Devolve TODOS os servidores de todos os usuários — só callers admin."""
    repo = repository or _default_repository()
    return await repo.list_all()


async def get_server(
    user_id: str, name: str, *, repository: McpServerRepositoryPort | None = None
) -> dict[str, Any] | None:
    """Devolve a entrada de `user_id`, ou `None` se não existir.

    Inclusive se `name` pertencer a outro usuário (REQ-001: nunca um
    vazamento entre usuários).
    """
    repo = repository or _default_repository()
    server = await repo.get(user_id, name)
    return _to_entry(server) if server is not None else None


async def add_server(
    user_id: str,
    name: str,
    *,
    transport: str = "stdio",
    command: str | None = None,
    args: list[str] | None = None,
    url: str | None = None,
    env: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
    repository: McpServerRepositoryPort | None = None,
) -> dict[str, Any]:
    """Adiciona um servidor novo para `user_id`.

    Raises:
        McpServerConfigError: `name` já cadastrado para ESSE `user_id` — outro
            usuário pode usar o mesmo nome sem colidir (REQ-001).
    """
    repo = repository or _default_repository()
    if await repo.get(user_id, name) is not None:
        raise McpServerConfigError(
            f"servidor '{name}' já existe para este usuário. Use update_server para editar."
        )

    server = McpServerConfig(
        id=str(uuid.uuid4()),
        user_id=user_id,
        name=name,
        transport=transport,
        command=command,
        args=list(args or []),
        url=url,
        env=dict(env or {}),
        headers=dict(headers or {}),
    )
    await repo.save(server)
    return _to_entry(server)


async def update_server(
    user_id: str,
    name: str,
    *,
    transport: str = "stdio",
    command: str | None = None,
    args: list[str] | None = None,
    url: str | None = None,
    env: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
    repository: McpServerRepositoryPort | None = None,
) -> dict[str, Any]:
    """Substitui a entrada de um servidor existente de `user_id`.

    Raises:
        McpServerConfigError: `name` não existe para ESSE `user_id` (inclusive
            se pertencer a outro usuário — REQ-001, não é um cross-user edit).
    """
    repo = repository or _default_repository()
    existing = await repo.get(user_id, name)
    if existing is None:
        raise McpServerConfigError(
            f"servidor '{name}' não existe para este usuário. Use add_server para criar."
        )

    server = McpServerConfig(
        id=existing.id,
        user_id=user_id,
        name=name,
        transport=transport,
        command=command,
        args=list(args or []),
        url=url,
        env=dict(env or {}),
        headers=dict(headers or {}),
        created_at=existing.created_at,
        updated_at=datetime.now(UTC),
    )
    await repo.save(server)
    return _to_entry(server)


async def delete_server(
    user_id: str, name: str, *, repository: McpServerRepositoryPort | None = None
) -> None:
    """Remove o servidor de `user_id`. Idempotente — não é erro remover o que não existe."""
    repo = repository or _default_repository()
    await repo.delete(user_id, name)


__all__ = [
    "McpServerConfigError",
    "add_server",
    "delete_server",
    "get_server",
    "list_all_servers",
    "list_servers",
    "update_server",
]
