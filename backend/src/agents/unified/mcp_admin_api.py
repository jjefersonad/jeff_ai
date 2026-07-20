"""API administrativa de servidores MCP — task `unified-agent-realignment-task-mcp-3`.

Roteador FastAPI montado no `image_server.py` (porta 8080), **não** no
grafo do agente. Esta é a fronteira que cumpre REQ-001 do `mcp-client`
("o agente não consegue adicionar/remover/modificar servidores por conta
própria"): o processo que roda o agente (`langgraph dev` / `unified`)
nunca importa este módulo, e nenhuma tool registrada no agente chama estas
rotas. Só o frontend (humano, via browser) fala com elas.

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

## Credenciais (REQ-007)

Os campos de `env` viajam como `{"chave": "NOME_DA_VAR_DE_AMBIENTE"}` em
ambas as direções — nunca o valor resolvido. `POST`/`PUT` recebem o NOME
da env var e gravam a referência `${NOME}` em `mcp_servers.json` (feito por
`mcp_config_store`); `GET` devolve a mesma referência crua, nunca chama
`os.environ`. O valor real do segredo não passa pela memória deste
processo em nenhum momento do fluxo de configuração.
"""
from __future__ import annotations

import asyncio
import re
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

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

router = APIRouter(prefix="/api/mcp", tags=["mcp"])

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

    `env` mapeia `{chave_no_servidor: nome_da_variavel_de_ambiente}` —
    NUNCA o valor. Ex.: `{"API_KEY": "MEU_SERVIDOR_API_KEY"}`.
    """

    command: str
    args: list[str] = []
    env: dict[str, str] = {}


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


# --------------------------------------------------------------------------- #
# Servidores
# --------------------------------------------------------------------------- #
@router.get("/servers")
async def get_servers() -> dict[str, Any]:
    """Lista servidores configurados com status ao vivo (REQ-001, REQ-004)."""
    servers = mcp_config_store.list_servers()

    async def _describe(name: str, entry: dict[str, Any]) -> dict[str, Any]:
        status = await _check_server(name, entry)
        return {
            "name": name,
            "command": entry.get("command", ""),
            "args": entry.get("args", []),
            "env": _env_display(entry.get("env") or {}),
            **status,
        }

    results = await asyncio.gather(*(_describe(n, e) for n, e in servers.items()))
    return {"servers": list(results)}


@router.post("/servers", status_code=201)
async def create_server(body: ServerCreateRequest) -> dict[str, Any]:
    try:
        entry = mcp_config_store.add_server(
            body.name, command=body.command, args=body.args, env_var_names=body.env
        )
    except McpServerConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"name": body.name, "command": entry["command"], "args": entry["args"], "env": body.env}


@router.put("/servers/{name}")
async def update_server(name: str, body: ServerWriteRequest) -> dict[str, Any]:
    try:
        entry = mcp_config_store.update_server(
            name, command=body.command, args=body.args, env_var_names=body.env
        )
    except McpServerConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"name": name, "command": entry["command"], "args": entry["args"], "env": body.env}


@router.delete("/servers/{name}", status_code=204)
async def delete_server(name: str) -> None:
    mcp_config_store.delete_server(name)


@router.get("/servers/{name}/tools")
async def get_server_tools(name: str) -> dict[str, Any]:
    entry = mcp_config_store.get_server(name)
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
