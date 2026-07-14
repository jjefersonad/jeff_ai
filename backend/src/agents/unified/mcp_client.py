"""Cliente MCP básico: conecta a servidores stdio declarados pelo usuário e lista as tools.

Cobre a task `unified-agent-realignment-task-mcp-1` (REQ-001, REQ-004, REQ-006,
REQ-007 do `mcp-client`). Escopo desta task: conectar e LISTAR. Injetar as
tools no loop do agente via `wrap_model_call` (Decision D5) é a task `mcp-2`;
a UI de configuração é a `mcp-3`.

## Fronteira

Isto NÃO tem relação com o `.mcp.json` da raiz do repositório — aquele é a
conexão do Claude Code (o assistente de desenvolvimento) ao servidor
OpenSddRag, com um bearer token de verdade dentro. O Jeff AI (o produto)
NUNCA lê esse arquivo. Servidores MCP configurados aqui são os que o
**usuário final do Jeff AI** quiser plugar no agente, e vivem em
`backend/mcp_servers.json` — um arquivo separado, propositalmente, para que
os dois nunca se confundam.

## Formato de `mcp_servers.json`

```json
{
  "mcpServers": {
    "nome-do-servidor": {
      "command": "npx",
      "args": ["-y", "@algum/mcp-server"],
      "env": {"API_KEY": "${ALGUM_API_KEY}"}
    }
  }
}
```

`env` aceita `${VAR}` — substituído por `os.environ["VAR"]` em runtime (lido
de `backend/.env` via `python-dotenv`, mesmo padrão do resto do código).
NUNCA coloque o valor do segredo diretamente no JSON — REQ-007 exige que
credenciais não apareçam em texto plano fora de `.env`.

## Q1 do design (RESPONDIDA pelo usuário, 2026-07-13)

Config em arquivo (`mcp_servers.json`), não banco — mesma convenção do
`.mcp.json` do Claude Code, sem UI na v1 (a UI vem em `mcp-3`). REQ-001
("editável sem alterar código-fonte") é satisfeito por edição do arquivo;
não exige um banco.

## Q2 do design (RESPONDIDA pelo usuário, 2026-07-13)

Só transporte `stdio` na v1. Um servidor configurado com outro transporte
(`http`, `sse`, `websocket`) é recusado com mensagem clara no carregamento
da config — REQ-006 proíbe falha silenciosa.
"""
from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.sessions import StdioConnection

_audit_log = logging.getLogger("jeff_ai.mcp_client")

# backend/mcp_servers.json — ao lado de backend/langgraph.json. Deliberadamente
# NÃO `.mcp.json`: evita qualquer confusão com o `.mcp.json` da raiz, que é do
# Claude Code e contém credenciais reais do OpenSddRag (ver docstring do módulo).
DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[3] / "mcp_servers.json"

_ENV_VAR_PATTERN = re.compile(r"^\$\{([A-Za-z_][A-Za-z0-9_]*)\}$")

_SUPPORTED_TRANSPORT = "stdio"


class McpConfigError(ValueError):
    """Configuração de servidor MCP inválida (transporte não suportado, campo faltando, etc.)."""


class McpServerConnectionError(RuntimeError):
    """Um servidor MCP específico falhou ao conectar ou listar tools (REQ-004).

    Isolado por servidor — um `McpServerConnectionError` para o servidor X
    não impede os demais de conectar. Ver `list_mcp_tools`.
    """

    def __init__(self, server_name: str, message: str) -> None:
        """Guarda `server_name` para o caller identificar qual servidor falhou."""
        self.server_name = server_name
        super().__init__(f"servidor MCP '{server_name}': {message}")


def _resolve_env_value(raw: str) -> str:
    """Substitui `${VAR}` por `os.environ['VAR']`.

    REQ-007: a única forma suportada de passar credencial é por referência a
    variável de ambiente — o VALOR nunca fica em texto plano no JSON. Um
    valor que não casa o padrão `${VAR}` é devolvido como está (permite
    valores não-secretos, ex. flags, hard-coded no config).
    """
    match = _ENV_VAR_PATTERN.match(raw)
    if match is None:
        return raw
    var_name = match.group(1)
    if var_name not in os.environ:
        raise McpConfigError(
            f"variável de ambiente '{var_name}' referenciada em "
            "mcp_servers.json não está definida (esperada em backend/.env)."
        )
    return os.environ[var_name]


def build_connection(name: str, entry: dict) -> StdioConnection:
    """Resolve UMA entrada de `mcpServers` para uma `StdioConnection`.

    Extraído de `load_mcp_server_config` para que a API administrativa
    (`mcp_admin_api.py`, task `mcp-3`) possa checar o status de UM servidor
    isoladamente — sem que um `env` faltando em OUTRO servidor do arquivo
    derrube a checagem deste. `load_mcp_server_config` usa isto internamente
    para manter o comportamento antigo (falha explícita ao carregar todos).

    Raises:
        McpConfigError: transporte diferente de `stdio` (REQ-006), campo
            `command` ausente, ou variável de ambiente referenciada em
            `env` não definida (REQ-007 — falha explícita, nunca silenciosa).
    """
    transport = entry.get("transport", _SUPPORTED_TRANSPORT)
    if transport != _SUPPORTED_TRANSPORT:
        raise McpConfigError(
            f"servidor MCP '{name}': transporte '{transport}' não é "
            f"suportado nesta versão do Jeff AI (só '{_SUPPORTED_TRANSPORT}'). "
            "Remova ou corrija a entrada em mcp_servers.json."
        )
    if "command" not in entry:
        raise McpConfigError(
            f"servidor MCP '{name}': falta o campo obrigatório 'command'."
        )

    raw_env = entry.get("env") or {}
    resolved_env = {k: _resolve_env_value(v) for k, v in raw_env.items()}

    return StdioConnection(
        transport="stdio",
        command=entry["command"],
        args=list(entry.get("args", [])),
        env=resolved_env or None,
    )


def load_mcp_server_config(
    path: Path | str = DEFAULT_CONFIG_PATH,
) -> dict[str, StdioConnection]:
    """Lê `mcp_servers.json` e devolve conexões stdio prontas para `MultiServerMCPClient`.

    Arquivo ausente → devolve `{}` (nenhum servidor configurado; não é erro —
    é o estado default de um Jeff AI recém-instalado, REQ-001 "sem alterar
    código-fonte" inclui "sem exigir o arquivo existir").

    Servidor com `transport` diferente de `stdio` → levanta `McpConfigError`
    com mensagem clara (REQ-006: recusa explícita, nunca falha silenciosa).

    Args:
        path: Caminho do config. Default `backend/mcp_servers.json`.
    """
    config_path = Path(path)
    if not config_path.exists():
        return {}

    raw = json.loads(config_path.read_text(encoding="utf-8"))
    servers = raw.get("mcpServers", {})

    return {name: build_connection(name, entry) for name, entry in servers.items()}


async def list_mcp_tools(
    connections: dict[str, StdioConnection],
) -> tuple[list[BaseTool], list[McpServerConnectionError]]:
    """Conecta a cada servidor e lista suas tools, isoladamente (REQ-004).

    Um servidor offline/lento/quebrado NÃO impede os demais: cada servidor é
    tentado em isolamento (loop com `try/except` por servidor, não uma única
    chamada para todos), e falhas viram entradas na lista de erros devolvida
    — não uma exceção que aborta a listagem inteira. O caller decide o que
    fazer com os erros (ex.: logar e avisar o usuário — REQ-004 "informado
    de qual servidor falhou e por quê").

    As credenciais resolvidas (`env`) NUNCA são incluídas nas mensagens de
    erro que construímos aqui — só o nome do servidor e o tipo/mensagem da
    exceção do cliente MCP (REQ-007). Isto não controla o que o PRÓPRIO
    processo do servidor eventualmente escreve em stderr; é responsabilidade
    de quem escreve o servidor MCP não vazar segredos ali.

    Returns:
        `(tools, errors)` — tools de TODOS os servidores que conectaram com
        sucesso, e a lista de falhas (uma por servidor problemático).
    """
    if not connections:
        return [], []

    client = MultiServerMCPClient(connections)
    tools: list[BaseTool] = []
    errors: list[McpServerConnectionError] = []

    for name in connections:
        try:
            server_tools = await client.get_tools(server_name=name)
        except Exception as exc:  # noqa: BLE001 — REQ-004: um servidor ruim não pode derrubar os outros
            _audit_log.warning(
                "mcp_audit event=connect_failed server=%r error_type=%s",
                name,
                type(exc).__name__,
            )
            errors.append(McpServerConnectionError(name, str(exc)))
            continue
        _audit_log.info(
            "mcp_audit event=connected server=%r tool_count=%d",
            name,
            len(server_tools),
        )
        tools.extend(server_tools)

    return tools, errors


__all__ = [
    "DEFAULT_CONFIG_PATH",
    "McpConfigError",
    "McpServerConnectionError",
    "build_connection",
    "list_mcp_tools",
    "load_mcp_server_config",
]
