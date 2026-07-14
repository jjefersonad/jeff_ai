"""CRUD de servidores MCP em `mcp_servers.json` — para a UI administrativa.

Cobre a task `unified-agent-realignment-task-mcp-3` (REQ-001 do
`mcp-client`: "o usuário adiciona, edita e remove servidores MCP pela
UI"). Este módulo é consumido exclusivamente por `mcp_admin_api.py`, que
roda no `image_server.py` — um processo HTTP separado do grafo do agente.
**Nenhuma tool do agente importa este módulo.** É assim que se cumpre "o
agente não consegue adicionar/remover/modificar servidores por conta
própria" — o agente simplesmente não tem alcance de código até aqui.

## Credenciais (REQ-007)

Este módulo nunca resolve `${VAR}` — essa resolução é responsabilidade
exclusiva de `mcp_client.load_mcp_server_config` (o caminho de runtime do
agente), lida direto de `os.environ` no momento de conectar. Aqui só
lemos/escrevemos o JSON cru, que por convenção do próprio `mcp_client`
NUNCA deve conter um valor de segredo em texto plano — só referências
`${VAR_NAME}`. A API administrativa (`mcp_admin_api.py`) aceita do
frontend apenas o NOME da variável de ambiente, nunca o valor, e monta a
referência `${VAR_NAME}` aqui.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.agents.unified.mcp_client import DEFAULT_CONFIG_PATH

_MCP_SERVERS_KEY = "mcpServers"

# Único transporte suportado na v1 (Q2 do design, `mcp_client._SUPPORTED_TRANSPORT`).
# Duplicado aqui (em vez de importar o símbolo privado) para não acoplar este
# módulo ao detalhe interno de `mcp_client`.
_SUPPORTED_TRANSPORT = "stdio"


class McpServerConfigError(ValueError):
    """Operação de CRUD inválida (nome duplicado, servidor inexistente, campo faltando)."""


def _read_raw(path: Path | str) -> dict[str, Any]:
    config_path = Path(path)
    if not config_path.exists():
        return {_MCP_SERVERS_KEY: {}}
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    raw.setdefault(_MCP_SERVERS_KEY, {})
    return raw


def _write_raw(path: Path | str, raw: dict[str, Any]) -> None:
    config_path = Path(path)
    config_path.write_text(json.dumps(raw, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def list_servers(path: Path | str = DEFAULT_CONFIG_PATH) -> dict[str, dict[str, Any]]:
    """Devolve as entradas cruas de `mcpServers` — `env` continua como `${VAR}`.

    Nunca resolve variáveis de ambiente (ver docstring do módulo). Seguro
    para expor à UI: o valor de qualquer segredo real nunca passa por aqui.
    """
    return dict(_read_raw(path)[_MCP_SERVERS_KEY])


def get_server(name: str, path: Path | str = DEFAULT_CONFIG_PATH) -> dict[str, Any] | None:
    """Devolve a entrada crua de um servidor, ou `None` se não existir."""
    return list_servers(path).get(name)


def _validate_entry(name: str, command: str, args: list[str], env_var_names: dict[str, str]) -> dict[str, Any]:
    if not name or not name.strip():
        raise McpServerConfigError("nome do servidor não pode ser vazio.")
    if not command or not command.strip():
        raise McpServerConfigError(f"servidor '{name}': o campo 'command' é obrigatório.")

    # Só stdio na v1 (Q2 do design) — a UI nem oferece outro transporte, mas
    # validamos aqui também para não depender só do frontend.
    env: dict[str, str] = {key: f"${{{var_name}}}" for key, var_name in env_var_names.items()}

    return {
        "transport": _SUPPORTED_TRANSPORT,
        "command": command,
        "args": list(args),
        "env": env,
    }


def add_server(
    name: str,
    *,
    command: str,
    args: list[str] | None = None,
    env_var_names: dict[str, str] | None = None,
    path: Path | str = DEFAULT_CONFIG_PATH,
) -> dict[str, Any]:
    """Adiciona um servidor novo. Recusa se `name` já existe.

    Args:
        name: identificador único do servidor.
        command: executável (ex. `npx`).
        args: argumentos do comando.
        env_var_names: `{chave_da_env_var_no_servidor: nome_da_var_de_ambiente}`.
            Ex.: `{"API_KEY": "MEU_SERVIDOR_API_KEY"}` grava
            `"env": {"API_KEY": "${MEU_SERVIDOR_API_KEY}"}` — a referência,
            nunca o valor (REQ-007).
        path: caminho do `mcp_servers.json`.

    Raises:
        McpServerConfigError: nome vazio, `command` ausente, ou nome já
            cadastrado.
    """
    raw = _read_raw(path)
    if name in raw[_MCP_SERVERS_KEY]:
        raise McpServerConfigError(f"servidor '{name}' já existe. Use update_server para editar.")

    entry = _validate_entry(name, command, args or [], env_var_names or {})
    raw[_MCP_SERVERS_KEY][name] = entry
    _write_raw(path, raw)
    return entry


def update_server(
    name: str,
    *,
    command: str,
    args: list[str] | None = None,
    env_var_names: dict[str, str] | None = None,
    path: Path | str = DEFAULT_CONFIG_PATH,
) -> dict[str, Any]:
    """Substitui a entrada de um servidor existente.

    Raises:
        McpServerConfigError: servidor não existe, ou `command` ausente.
    """
    raw = _read_raw(path)
    if name not in raw[_MCP_SERVERS_KEY]:
        raise McpServerConfigError(f"servidor '{name}' não existe. Use add_server para criar.")

    entry = _validate_entry(name, command, args or [], env_var_names or {})
    raw[_MCP_SERVERS_KEY][name] = entry
    _write_raw(path, raw)
    return entry


def delete_server(name: str, path: Path | str = DEFAULT_CONFIG_PATH) -> None:
    """Remove um servidor. Idempotente — não é erro remover o que não existe."""
    raw = _read_raw(path)
    raw[_MCP_SERVERS_KEY].pop(name, None)
    _write_raw(path, raw)


__all__ = [
    "McpServerConfigError",
    "add_server",
    "delete_server",
    "get_server",
    "list_servers",
    "update_server",
]
