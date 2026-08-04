"""API administrativa de servidores MCP.

task `unified-agent-realignment-task-mcp-3`,
revisado por `user-scoped-mcp-config-storage-task-admin-1`.

Roteador FastAPI montado em `webapp.py` (`retire-image-server-task-core-1`
— antes vivia sozinho em `image_server.py`, processo separado, hoje
aposentado). REQ-001 do `mcp-client` ("o agente não consegue adicionar/
remover/modificar servidores por conta própria") deixou de depender de
isolamento físico de processo: agora é garantido por `require_auth`
(nenhuma tool do agente tem acesso ao cookie de sessão do browser) e,
independentemente, por `test_mcp_admin_import_boundary.py` (nenhum módulo
de `src/tools`/`src/agents`/`src/composition`, fora deste arquivo e de
`mcp_config_store.py`, pode importar este módulo). Só o frontend (humano,
via browser, com sessão válida) fala com estas rotas.

## Endpoints

- `GET  /api/mcp/servers` — lista servidores configurados + status
  (conectado/offline/erro) + contagem de tools.
- `POST /api/mcp/servers` — adiciona um servidor.
- `PUT  /api/mcp/servers/{name}` — edita um servidor.
- `DELETE /api/mcp/servers/{name}` — remove um servidor.
- `GET  /api/mcp/servers/{name}/tools` — lista as tools de um servidor,
  com nome, descrição e capacidade classificada (via `effects.classify()` —
  override manual se houver, senão `network` por default para tool MCP,
  desde `remove-mcp-unknown-failsafe`).
- `GET  /api/mcp/capabilities` — capacidades válidas (para o combobox da UI).
- `GET  /api/mcp/tools/overrides` — todos os overrides gravados.
- `POST /api/mcp/tools/capability` — classifica manualmente uma tool MCP.
- `DELETE /api/mcp/tools/capability/{tool_name}` — remove a classificação.

## Auth (`scoped-mcp-config` REQ-001, task-admin-1)

Desde `user-scoped-mcp-config-storage-task-admin-1`, o router tem
`Depends(require_auth)` aplicado a TODAS as rotas — toda chamada exige
sessão válida (mesmo mecanismo do `webapp.py`). O processo
`image_server.py` (única montagem em produção) provê o pool de auth via
lifespan, mesmo padrão do `_lifespan` de `webapp.py`.

## user_id Scoping (task-admin-2)

Cada handler extrai `user_id` do `User` injectado por `require_auth`.
Admin (`role=admin`) pode listar servidores de todos os usuários
(metadata only — nunca `env`/`headers` decifrados); non-admin só vê os
seus próprios. POST/PUT/DELETE operam exclusivamente no `user_id` do
requester — nunca um valor de outro usuário.

## Credenciais

A partir de `user-scoped-mcp-config-storage-task-store-2`, valores
sensíveis (`env` para stdio, `headers` para http) são cifrados em repouso
pelo `PostgresMcpServerRepository` (Fernet via `credentials_crypto`),
não mais referenciados como `${VAR}` em `mcp_servers.json` — esse
arquivo não existe mais como caminho de leitura. O `_env_display()` deste
módulo continua exibindo só o NOME da variável (`${VAR}` → `VAR`),
nunca o valor resolvido.
"""
from __future__ import annotations

import asyncio
import re
from typing import Any, Literal, Self

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator

from src.agents.unified import mcp_config_store
from src.agents.unified.effects import CAPABILITY_NAMES, classify
from src.agents.unified.mcp_client import (
    McpConfigError,
    build_connection,
    list_mcp_tools,
)
from src.agents.unified.mcp_config_store import McpServerConfigError
from src.agents.unified.mcp_tool_overrides import (
    McpOverrideError,
    load_overrides,
    remove_override,
    set_override,
)
from src.application.mcp.mcp_server_schema import McpServerEntryConfig
from src.infrastructure.auth.dependencies import require_auth
from src.infrastructure.auth.users import User

# Gate de auth no router — `scoped-mcp-config` REQ-001 (task-admin-1).
# Toda rota `/api/mcp/*` exige sessão válida, mesmo mecanismo de resolução
# usado por `webapp.py`. `require_auth` devolve o `User` autenticado (ou
# `None` se o path bate `PUBLIC_PATHS`, o que não se aplica a `/api/mcp/*`).
# Redundante com a dependency global de `webapp.py` desde
# `retire-image-server-task-core-1` — mantido aqui também porque é barato e
# deixa o router correto por si só, sem depender de onde for montado.
router = APIRouter(
    prefix="/api/mcp",
    tags=["mcp"],
    dependencies=[Depends(require_auth)],
)

# Tempo máximo para tentar conectar a um servidor ao checar status/listar
# tools (REQ-004: "trava durante a chamada" → falha com erro claro dentro
# de um timeout, o resto do sistema segue).
_CONNECT_TIMEOUT_SECONDS = 8.0

_ENV_REF_PATTERN = re.compile(r"^\$\{([A-Za-z_][A-Za-z0-9_]*)\}$")


# --------------------------------------------------------------------------- #
# Schemas
# --------------------------------------------------------------------------- #
class ServerWriteRequest(BaseModel):
    """Corpo de `POST /servers` e `PUT /servers/{name}`.

    Discriminado por `transport` (default `stdio` para clientes legados):
    - `stdio` — exige `command`; `args`/`env` opcionais.
    - `http` — exige `url`; `headers` opcional (sem exigir `command`).

    Regras alinhadas a `McpServerEntryConfig` / ao `ServerWritePayload` do
    frontend (`fix-mcp-http-server-admin-api`).
    """

    transport: Literal["stdio", "http"] = "stdio"
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    url: str | None = None
    env: dict[str, str] = Field(default_factory=dict)
    headers: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_transport_fields(self) -> Self:
        McpServerEntryConfig(
            transport=self.transport,
            command=self.command,
            args=self.args,
            url=self.url,
            env=self.env,
            headers=self.headers,
        )
        return self


class ServerCreateRequest(ServerWriteRequest):
    name: str


class CapabilityRequest(BaseModel):
    tool_name: str
    capability: str


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _env_display(raw_env: dict[str, Any]) -> dict[str, str]:
    """Extrai o NOME da variável de uma referência `${VAR}` para exibição.

    Valores que não seguem o padrão `${VAR}` (flags não-secretas, ver
    `mcp_client._resolve_env_value`) são devolvidos como estão — nunca são
    segredo por convenção do próprio `mcp_client`.
    """
    display: dict[str, str] = {}
    for key, value in raw_env.items():
        match = _ENV_REF_PATTERN.match(value) if isinstance(value, str) else None
        display[key] = match.group(1) if match else value
    return display


def _headers_display(raw_headers: dict[str, Any]) -> dict[str, str]:
    """Exibe headers sem ecoar valores secretos em claro.

    Referências `${VAR}` viram o nome da variável; qualquer outro valor
    (ex.: `Bearer …` colado no form) é mascarado como `***`.
    """
    display: dict[str, str] = {}
    for key, value in raw_headers.items():
        if isinstance(value, str):
            match = _ENV_REF_PATTERN.match(value)
            display[key] = match.group(1) if match else "***"
        else:
            display[key] = "***"
    return display


def _server_write_response(name: str, entry: dict[str, Any]) -> dict[str, Any]:
    """Resposta de create/update — metadados por transporte, sem segredos."""
    return {
        "Name": name,
        "transport": entry.get("transport") or "stdio",
        "command": entry.get("command") or "",
        "args": list(entry.get("args") or []),
        "url": entry.get("url") or "",
        "env": _env_display(entry.get("env") or {}),
        "headers": _headers_display(entry.get("headers") or {}),
    }


def _qualify(server_name: str, tool_name: str) -> str:
    """Mesmo esquema de `mcp_tools_middleware._qualify_tool_names`."""
    safe_server = server_name.replace("-", "_")
    return f"mcp__{safe_server}__{tool_name}"


async def _check_server(name: str, entry: dict[str, Any]) -> dict[str, Any]:
    """Tenta conectar a UM servidor e devolve status + contagem de tools.

    Isola falhas (REQ-004): um `McpConfigError` (env var faltando,
    transporte não suportado) ou um timeout de conexão viram
    `status="error"`/`"offline"`, nunca uma exceção que derruba a
    listagem dos outros servidores.
    """
    try:
        connection = build_connection(name, entry)
    except McpConfigError as exc:
        return {"status": "error", "message": str(exc), "tool_count": 0}

    try:
        tools, errors = await asyncio.wait_for(
            list_mcp_tools({name: connection}), timeout=_CONNECT_TIMEOUT_SECONDS
        )
    except TimeoutError:
        return {
            "status": "offline",
            "message": f"timeout após {_CONNECT_TIMEOUT_SECONDS:.0f}s tentando conectar",
            "tool_count": 0,
        }

    if errors:
        return {"status": "error", "message": str(errors[0]), "tool_count": 0}
    return {"status": "connected", "message": None, "tool_count": len(tools)}


async def _server_entry(server) -> dict[str, Any]:
    """Convert a `McpServerConfig` to a dict for `build_connection`."""
    return {
        "transport": server.transport,
        "command": server.command,
        "args": list(server.args),
        "url": server.url,
        "env": dict(server.env),
        "headers": dict(server.headers),
    }


# --------------------------------------------------------------------------- #
# Servidores
# --------------------------------------------------------------------------- #
@router.get("/servers")
async def get_servers(user: User = Depends(require_auth)) -> dict[str, Any]:
    """Lista servidores configurados com status ao vivo (REQ-001, REQ-004).

    Scoping: admin vê todos os usuários (metadata only); non-admin vê só os seus.
    Nunca devolve valor decifrado de `env`/`headers`.
    """
    is_admin = user is not None and user.role == "admin"

    async def _describe(name: str, entry: dict[str, Any]) -> dict[str, Any]:
        status = await _check_server(name, entry)
        return {
            "name": name,
            "transport": entry.get("transport") or "stdio",
            "command": entry.get("command") or "",
            "args": entry.get("args") or [],
            "url": entry.get("url") or "",
            "env": _env_display(entry.get("env") or {}),
            "headers": _headers_display(entry.get("headers") or {}),
            **status,
        }

    if is_admin:
        # Admin: list across all users via list_all_servers() — metadata only
        all_servers = await mcp_config_store.list_all_servers()
        entries = [(s.name, await _server_entry(s)) for s in all_servers]
    else:
        # Non-admin: list only the requesting user's servers
        assert user is not None
        user_entries = await mcp_config_store.list_servers(user.id)
        entries = list(user_entries.items())

    results = await asyncio.gather(*(_describe(n, e) for n, e in entries))
    return {"servers": list(results)}


@router.post("/servers", status_code=201)
async def create_server(
    body: ServerCreateRequest, user: User = Depends(require_auth)
) -> dict[str, Any]:
    if user is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        entry = await mcp_config_store.add_server(
            user.id,
            body.name,
            transport=body.transport,
            command=body.command,
            args=body.args,
            url=body.url,
            env=body.env,
            headers=body.headers,
        )
    except McpServerConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _server_write_response(body.name, entry)


@router.put("/servers/{name}")
async def update_server(
    name: str, body: ServerWriteRequest, user: User = Depends(require_auth)
) -> dict[str, Any]:
    if user is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        entry = await mcp_config_store.update_server(
            user.id,
            name,
            transport=body.transport,
            command=body.command,
            args=body.args,
            url=body.url,
            env=body.env,
            headers=body.headers,
        )
    except McpServerConfigError as exc:
        # "não existe" → 404 (scoped to user's rows); "já existe" → 400
        if "não existe" in str(exc):
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _server_write_response(name, entry)


@router.delete("/servers/{name}", status_code=204, response_model=None)
async def delete_server(name: str, user: User = Depends(require_auth)) -> None:
    if user is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    await mcp_config_store.delete_server(user.id, name)


@router.get("/servers/{name}/tools")
async def get_server_tools(
    name: str, user: User = Depends(require_auth)
) -> dict[str, Any]:
    if user is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    entry = await mcp_config_store.get_server(user.id, name)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"servidor '{name}' não configurado.")

    try:
        connection = build_connection(name, entry)
    except McpConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        tools, errors = await asyncio.wait_for(
            list_mcp_tools({name: connection}), timeout=_CONNECT_TIMEOUT_SECONDS
        )
    except TimeoutError as exc:
        raise HTTPException(
            status_code=504,
            detail=f"timeout após {_CONNECT_TIMEOUT_SECONDS:.0f}s tentando conectar a '{name}'",
        ) from exc

    if errors:
        raise HTTPException(status_code=502, detail=str(errors[0])) from None

    out = []
    for tool in tools:
        qualified = _qualify(name, tool.name)
        out.append(
            {
                "name": tool.name,
                "qualified_name": qualified,
                "description": tool.description or "",
                # Consulta `effects.classify()` de verdade em vez de assumir
                # "unknown" como fallback hardcoded — desde
                # `remove-mcp-unknown-failsafe`, uma tool MCP sem override
                # classifica como `network` por default, não `unknown`.
                # Um fallback fixo aqui mentiria sobre o estado real da tool.
                "capability": classify(qualified)[0].value,
            }
        )
    return {"server": name, "tools": out}


# --------------------------------------------------------------------------- #
# Classificação manual de capacidade (Q3 do design)
# --------------------------------------------------------------------------- #
@router.get("/capabilities")
async def get_capabilities() -> dict[str, Any]:
    """Capacidades válidas — para o combobox de classificação da UI."""
    return {"capabilities": list(CAPABILITY_NAMES)}


@router.get("/tools/overrides")
async def get_overrides() -> dict[str, Any]:
    return {"overrides": load_overrides()}


@router.post("/tools/capability")
async def put_capability(body: CapabilityRequest) -> dict[str, Any]:
    """Classifica manualmente uma tool MCP (ato humano — ver docstring do módulo)."""
    try:
        overrides = set_override(
            body.tool_name, body.capability, valid_capabilities=CAPABILITY_NAMES
        )
    except McpOverrideError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"overrides": overrides}


@router.delete("/tools/capability/{tool_name:path}")
async def delete_capability(tool_name: str) -> dict[str, Any]:
    overrides = remove_override(tool_name)
    return {"overrides": overrides}


__all__ = ["router"]
