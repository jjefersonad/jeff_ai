"""`McpToolsMiddleware` — injeção de tools MCP no grafo via `wrap_model_call`.

Corresponde à task `unified-agent-realignment-task-mcp-2` e à **Decision D5**
do design: como o gate G1 passa (`ModelRequest.override(tools=[...])`), NÃO é
preciso rebuildar o grafo para adicionar um servidor — as tools MCP são
injetadas a cada chamada do modelo, em runtime.

## Responsabilidades

1. **Carregar servidores MCP** configurados em `backend/mcp_servers.json` via
   `load_mcp_server_config()` do `mcp_client`.
2. **Listar as tools** de cada servidor via `list_mcp_tools()`.
3. **Injetar as tools MCP** no `ModelRequest.tools` via `wrap_model_call`,
   qualificando o nome por servidor de origem para evitar colisão com tools
   nativas (REQ-002).
4. **Degradar graciosamente** se um servidor estiver offline/lento (REQ-004) —
   o agente inicia normalmente, sem as tools daquele servidor, e o usuário é
   informado.
5. **Sujeitar as tools MCP ao envelope** — isso acontece automaticamente porque
   o `EnvelopeMiddleware` roda DEPOIS deste e filtra o set combinado (nativas +
   MCP) antes de entregá-lo ao modelo. Ver ordem de composição em
   `agent.py:middleware=[McpToolsMiddleware(), EnvelopeMiddleware()]`.

## REQ-003: classificação por default para tools MCP desconhecidas

Toda tool MCP NÃO catalogada no `TOOL_EFFECTS` e sem override manual em
`mcp_tool_overrides.json` é classificada como `Capability.NETWORK` pelo
`effects.classify()` — piso, decisão explícita do usuário revista pela
change `remove-mcp-unknown-failsafe` (o comportamento anterior era
`UNKNOWN`, fail-safe). Como `NETWORK` está em `FLOOR_CAPABILITIES`, a tool:
- **É exposta** ao modelo mesmo sem envelope concedido (passa direto pelo
  `EnvelopeMiddleware`, que trata o piso como "sem atrito onde não há
  risco declarado");
- **Executa sem gate de tier** por essa via — o piso não depende de
  aprovação por tarefa.

Ou seja: qualquer tool de um servidor MCP configurado em `mcp_servers.json`
fica utilizável assim que o servidor conecta, sem exigir classificação
manual prévia. Quem quiser restringir uma tool MCP específica mais do que
o piso (`write_existing`, `vcs`, `shell`) usa `mcp_tool_overrides.json` —
a classificação manual continua tendo precedência sobre o default
`NETWORK`. Isto fecha o REQ-003 do `mcp-client` e o REQ-008 (revisto) do
`task-scoped-permissions`.

## REQ-005: carregamento em runtime, sem restart

Como este middleware roda a cada `wrap_model_call`, adicionar um servidor
novo ao `mcp_servers.json` torna suas tools disponíveis **na próxima chamada
do modelo** — sem rebuild do grafo, sem restart do backend. A prova está no
teste `test_mcp_tools_middleware_hot_reload`.

## Qualificação de nomes (REQ-002)

Um servidor MCP pode expor uma tool chamada `edit_file`, que já existe
nativamente. Para evitar ambiguidade e sobrescrita, o nome da tool MCP é
qualificado por servidor:

- Servidor `meu-servidor` expõe tool `edit_file` →
  `mcp__meu_servidor__edit_file`.
- Tool nativa `edit_file` → permanece `edit_file`.

As duas coexistem sem colisão. O modelo vê ambas e pode escolher qual usar.

## Ordem de composição no grafo

```
create_deep_agent(
    middleware=[
        McpToolsMiddleware(),      # <- adiciona tools MCP ao set
        EnvelopeMiddleware(),      # <- filtra nativas + MCP pelo envelope
    ]
)
```

O deepagents monta a pilha de middleware na ordem **inversa** da lista —
então `EnvelopeMiddleware` roda PRIMEIRO (mais próximo do modelo), e
`McpToolsMiddleware` roda ANTES dele na cadeia. Resultado:

1. `McpToolsMiddleware.wrap_model_call` → adiciona tools MCP ao `request.tools`.
2. `EnvelopeMiddleware.wrap_model_call` → filtra o set combinado pelo envelope.
3. O modelo vê só as tools (nativas e MCP) que passaram no filtro.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Sequence
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ModelRequest
from langchain_core.tools import BaseTool

from src.agents.unified.mcp_client import (
    DEFAULT_CONFIG_PATH,
    McpServerConnectionError,
    list_mcp_tools,
    load_mcp_server_config,
)

_audit_log = logging.getLogger("jeff_ai.mcp_tools_middleware")


class McpToolsMiddleware(AgentMiddleware[Any, Any, Any]):
    """Injeta tools de servidores MCP no set do modelo via `wrap_model_call`.

    A instanciação é trivial — sem parâmetros, sem estado mutável. O
    middleware lê `backend/mcp_servers.json` a cada `wrap_model_call` e
    carrega as tools dos servidores configurados. Isto permite hot-reload
    (REQ-005): adicionar um servidor novo torna suas tools disponíveis na
    próxima chamada do modelo, sem restart.

    Parameters
    ----------
    config_path:
        Caminho do arquivo de configuração de servidores MCP. Default:
        `backend/mcp_servers.json`. Útil para testes que queiram
        substituir o config real por um mock.
    qualify_names:
        Se `True` (default), qualifica os nomes das tools MCP por servidor
        de origem (`mcp__servidor__tool`). Se `False`, usa o nome original
        da tool — útil para testes, mas cria risco de colisão em produção.

    Attributes
    ----------
    connection_errors:
        Lista de `McpServerConnectionError` do último carregamento. Vazia
        se todos os servidores conectaram com sucesso. Útil para auditoria
        e para expor ao usuário quais servidores falharam (REQ-004).
    """

    def __init__(
        self,
        config_path: str | None = None,
        *,
        qualify_names: bool = True,
    ) -> None:
        """Inicializa o middleware.

        Ver a docstring da classe para os parâmetros.
        """
        super().__init__()
        self._config_path = config_path or str(DEFAULT_CONFIG_PATH)
        self._qualify_names = qualify_names
        # Lista de falhas do último carregamento (REQ-004 auditoria).
        self.connection_errors: list[McpServerConnectionError] = []

    def _load_mcp_tools(self) -> list[BaseTool]:
        """Carrega tools de todos os servidores MCP configurados.

        Servidores offline/lentos são isolados — um servidor ruim não
        impede os demais de conectar. Falhas são acumuladas em
        `self.connection_errors` para auditoria (REQ-004).

        Returns:
            Lista de tools de TODOS os servidores que conectaram com
            sucesso, com nomes qualificados por servidor de origem
            (se `qualify_names=True`).
        """
        try:
            connections = load_mcp_server_config(self._config_path)
        except Exception as exc:
            # Config inválida ou arquivo faltando/malformado. Loga mas não trava.
            _audit_log.error(
                "mcp_tools_middleware event=config_load_failed error=%s",
                str(exc),
                exc_info=True,
            )
            self.connection_errors = []
            return []

        if not connections:
            # Nenhum servidor configurado — estado default de um Jeff AI
            # recém-instalado (REQ-001). Não é erro.
            self.connection_errors = []
            return []

        # `list_mcp_tools` é async — precisa rodar num event loop.
        # Como `wrap_model_call` é síncrono, sempre usa `asyncio.run`
        # para criar um loop temporário. Se houver um loop já rodando
        # (caso raro em sync path), tenta usar nest_asyncio ou fallback.
        try:
            tools, errors = asyncio.run(list_mcp_tools(connections))
        except RuntimeError as e:
            if "already running" in str(e):
                # Loop já rodando — não deveria acontecer em sync path,
                # mas se acontecer, devolve vazio e loga o erro.
                _audit_log.error(
                    "mcp_tools_middleware event=sync_in_async_context "
                    "error=cannot_run_async_in_sync_wrapper"
                )
                tools, errors = [], []
            else:
                raise

        self.connection_errors = errors

        # Loga servidores que falharam (REQ-004 "informar qual e por quê").
        for err in errors:
            _audit_log.warning(
                "mcp_tools_middleware event=server_failed server=%r error=%s",
                err.server_name,
                str(err),
            )

        # Qualifica os nomes se `qualify_names=True` (REQ-002 anti-colisão).
        if self._qualify_names:
            tools = _qualify_tool_names(tools, connections)

        _audit_log.info(
            "mcp_tools_middleware event=tools_loaded tool_count=%d server_errors=%d",
            len(tools),
            len(errors),
        )
        return tools

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Any],
    ) -> Any:
        """Versão síncrona: adiciona tools MCP ao set do modelo."""
        mcp_tools = self._load_mcp_tools()
        combined = list(request.tools or []) + mcp_tools
        return handler(request.override(tools=combined))

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Any],
    ) -> Any:
        """Versão assíncrona — **obrigatória em produção**.

        O langchain 1.x NÃO faz bridge automático de `wrap_model_call`
        (sync) para contexto async. O `langgraph-api` roda o grafo via
        `astream()`/`ainvoke()` sempre — então sem este método o grafo
        quebra em toda chamada de modelo. Ver `EnvelopeMiddleware` para
        o mesmo padrão.
        """
        # Versão async de `_load_mcp_tools`: chama `list_mcp_tools` direto.
        try:
            connections = load_mcp_server_config(self._config_path)
        except Exception as exc:
            _audit_log.error(
                "mcp_tools_middleware event=config_load_failed error=%s",
                str(exc),
                exc_info=True,
            )
            self.connection_errors = []
            return await handler(request)

        if not connections:
            self.connection_errors = []
            return await handler(request)

        tools, errors = await list_mcp_tools(connections)
        self.connection_errors = errors

        for err in errors:
            _audit_log.warning(
                "mcp_tools_middleware event=server_failed server=%r error=%s",
                err.server_name,
                str(err),
            )

        if self._qualify_names:
            tools = _qualify_tool_names(tools, connections)

        _audit_log.info(
            "mcp_tools_middleware event=tools_loaded tool_count=%d server_errors=%d",
            len(tools),
            len(errors),
        )

        combined = list(request.tools or []) + tools
        return await handler(request.override(tools=combined))


def _qualify_tool_names(
    tools: Sequence[BaseTool],
    connections: dict[str, Any],
) -> list[BaseTool]:
    """Qualifica os nomes das tools MCP por servidor de origem.

    Formato: `mcp__<servidor>__<tool>` (REQ-002 anti-colisão).

    O `MultiServerMCPClient` do `langchain_mcp_adapters` já qualifica
    as tools internamente quando há múltiplos servidores — mas o formato
    é `<servidor>/<tool>`, não `mcp__<servidor>__<tool>`. Para manter a
    convenção usada em outros lugares do Jeff AI (ex.: o padrão
    `mcp__opensddrag__*` do OpenSddRag MCP server), re-nomeamos aqui.

    Args:
        tools: Tools devolvidas por `list_mcp_tools()`.
        connections: Dict `{servidor: StdioConnection}`, usado para
            descobrir a qual servidor cada tool pertence.

    Returns:
        Lista de tools com nomes qualificados. A tool é clonada (via
        `tool.copy()`) para não mutar o objeto original.
    """
    qualified: list[BaseTool] = []
    for tool in tools:
        # O `MultiServerMCPClient` já qualifica como `servidor/tool`.
        # Detectamos isso e re-qualificamos no padrão `mcp__servidor__tool`.
        original_name = tool.name
        if "/" in original_name:
            # Ex.: "meu-servidor/edit_file" → "mcp__meu_servidor__edit_file"
            server, _, tool_name = original_name.partition("/")
            # Normaliza o nome do servidor: hífens → underscores (válido em Python).
            safe_server = server.replace("-", "_")
            new_name = f"mcp__{safe_server}__{tool_name}"
        else:
            # Tool sem servidor no nome (não deveria acontecer com
            # `MultiServerMCPClient`, mas fail-safe).
            # Tenta inferir do primeiro servidor configurado (heurística fraca).
            if connections:
                first_server = next(iter(connections))
                safe_server = first_server.replace("-", "_")
                new_name = f"mcp__{safe_server}__{original_name}"
            else:
                new_name = f"mcp__unknown__{original_name}"

        # Clona a tool com o nome novo. Usa `model_copy` (Pydantic v2).
        try:
            # Pydantic v2
            qualified_tool = tool.model_copy(update={"name": new_name})
        except AttributeError:
            # Fallback para Pydantic v1
            qualified_tool = tool.copy(update={"name": new_name})
        qualified.append(qualified_tool)

    return qualified


__all__ = ["McpToolsMiddleware"]
