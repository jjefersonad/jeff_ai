"""`McpToolsMiddleware` — injeção de tools MCP no grafo via `wrap_model_call`.

Corresponde à task `unified-agent-realignment-task-mcp-2` e à **Decision D5**
do design: como o gate G1 passa (`ModelRequest.override(tools=[...])`), NÃO é
preciso rebuildar o grafo para adicionar um servidor — as tools MCP são
injetadas a cada chamada do modelo, em runtime.

## Responsabilidades

1. **Resolver o `user_id` da sessão** via `resolve_user_id()`
   (`src/infrastructure/ownership/store.py`) e **carregar os servidores MCP**
   daquele usuário (Postgres, `user_mcp_servers`) via `load_mcp_server_config()`
   do `mcp_client` — revisado pela task `user-scoped-mcp-config-storage-task-middleware-1`
   (REQ-009); antes lia um `backend/mcp_servers.json` único e compartilhado.
   `user_id` não resolvido (sessão sem vínculo, ex.: canal Telegram/WhatsApp
   ainda não linkado) → zero servidores carregados, sem erro.
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
novo para um usuário (via a API administrativa, `mcp_admin_api.py`) torna
suas tools disponíveis **na próxima chamada do modelo daquele usuário** —
sem rebuild do grafo, sem restart do backend.

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
import re
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ModelRequest, ToolCallRequest
from langchain_core.tools import BaseTool

from src.agents.unified.mcp_client import (
    McpServerConnectionError,
    list_mcp_tools,
    load_mcp_server_config,
)
from src.infrastructure.ownership.store import resolve_user_id

_audit_log = logging.getLogger("jeff_ai.mcp_tools_middleware")

# Registry leve para a tool `list_mcp_servers_status` (Decision 4 da change
# `fix-mcp-tool-not-exposed-error`) conseguir descobrir a instância
# ativa. Module-level (não atributo de classe) — Python nativo permite
# atribuição. Idempotente: cada nova instância sobrescreve. Não é
# thread-safe (deepagents cria uma instância por `astream()` — não é o
# uso concorrente).
_LATEST_INSTANCE: "McpToolsMiddleware | None" = None


class McpToolsMiddleware(AgentMiddleware[Any, Any, Any]):
    """Injeta tools de servidores MCP no set do modelo via `wrap_model_call`.

    A instanciação é trivial — sem parâmetros obrigatórios, sem estado
    mutável. A cada `wrap_model_call`, o middleware resolve o `user_id` da
    sessão corrente (`resolve_user_id()`) e carrega os servidores MCP
    daquele usuário. Isto permite hot-reload (REQ-005): adicionar um
    servidor novo para um usuário torna suas tools disponíveis na próxima
    chamada do modelo daquele usuário, sem restart.

    Parameters
    ----------
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
    last_load_status:
        Snapshot serializável do último carregamento — alimentado em
        `_aload_mcp_tools`/`_load_mcp_tools` (e portanto em cada
        `wrap_model_call`/`awrap_model_call`). Consumido pelo
        `McpToolAvailabilityMiddleware` (change
        `fix-mcp-tool-not-exposed-error`, Decision 3) pra categorizar
        erros `mcp__*` em runtime. Shape:
        `{loaded_at: ISO8601, servers: dict[server_name, status],
          tools_by_name: dict[qualified_name, server_name]}`
    """

    def __init__(
        self,
        *,
        qualify_names: bool = True,
    ) -> None:
        """Inicializa o middleware.

        Ver a docstring da classe para os parâmetros.
        """
        super().__init__()
        self._qualify_names = qualify_names
        # Lista de falhas do último carregamento (REQ-004 auditoria).
        self.connection_errors: list[McpServerConnectionError] = []
        # Snapshot serializável do último carregamento (Decision 3 da change
        # `fix-mcp-tool-not-exposed-error`). Inicializado vazio — qualquer
        # leitura antes da primeira chamada ao grafo vê o estado default.
        self.last_load_status: dict[str, Any] = {}
        # Tools MCP do último load, indexadas pelo nome qualificado. O
        # ToolNode só conhece `_UNIFIED_TOOLS` estáticas — `wrap_tool_call`
        # injeta estas instâncias em `request.tool` para execução dinâmica
        # (padrão suportado pelo ToolNode para tools de middleware).
        self._loaded_tools: dict[str, BaseTool] = {}
        # Registra esta instância no module-level registry (Decision 4 da
        # mesma change) — a tool `list_mcp_servers_status` consulta via
        # `get_latest()` pra descobrir a instância ativa.
        global _LATEST_INSTANCE
        _LATEST_INSTANCE = self

    @classmethod
    def get_latest(cls) -> "McpToolsMiddleware | None":
        """Devolve a instância registrada mais recentemente, ou `None` se
        nenhuma existir ainda (ex.: pré-grafo)."""
        return _LATEST_INSTANCE

    async def _aload_mcp_tools(self) -> list[BaseTool]:
        """Resolve o `user_id` da sessão corrente e carrega as tools MCP dele.

        Compartilhado entre a via síncrona (`_load_mcp_tools`, via
        `asyncio.run`) e a assíncrona (`awrap_model_call`, `await` direto) —
        uma única implementação da resolução de identidade + carregamento
        (REQ-009), sem duplicar a lógica entre as duas.

        `resolve_user_id()` devolvendo `None` (sessão sem vínculo, ex.: canal
        Telegram/WhatsApp ainda não linkado) é o mesmo estado default de
        "nenhum servidor configurado" — zero tools, sem erro.

        Servidores offline/lentos são isolados — um servidor ruim não
        impede os demais de conectar. Falhas são acumuladas em
        `self.connection_errors` para auditoria (REQ-004).

        Returns:
            Lista de tools de TODOS os servidores do usuário que
            conectaram com sucesso, com nomes qualificados por servidor de
            origem (se `qualify_names=True`).
        """
        user_id = await resolve_user_id()
        if user_id is None:
            self.connection_errors = []
            self._loaded_tools = {}
            self.last_load_status = self._build_empty_status()
            self._publish_load_status()
            return []

        connections = await load_mcp_server_config(user_id)
        if not connections:
            # Usuário sem nenhum servidor configurado. Não é erro.
            self.connection_errors = []
            self._loaded_tools = {}
            self.last_load_status = self._build_empty_status()
            self._publish_load_status()
            return []

        tools, errors = await list_mcp_tools(connections)
        self.connection_errors = errors

        # Loga servidores que falharam (REQ-004 "informar qual e por quê").
        # O `last_error` construído aqui NÃO inclui o `McpServerConnectionError`
        # cru — só o nome e o tipo da exceção — para defender a REQ-007 do
        # `mcp-client` (sem leak de credenciais) caso a mensagem do erro do
        # vendor contenha valores de `env`/`headers`.
        for err in errors:
            safe_error = redact_credentials(err)
            _audit_log.warning(
                "mcp_tools_middleware event=server_failed server=%r error=%s",
                err.server_name,
                safe_error,
            )

        # Qualifica os nomes se `qualify_names=True` (REQ-002 anti-colisão).
        if self._qualify_names:
            tools = _qualify_tool_names(tools, connections)

        _audit_log.info(
            "mcp_tools_middleware event=tools_loaded tool_count=%d server_errors=%d",
            len(tools),
            len(errors),
        )

        # Snapshot serializável para o `McpToolAvailabilityMiddleware`
        # (Decision 3 da change `fix-mcp-tool-not-exposed-error`).
        self._loaded_tools = {tool.name: tool for tool in tools}
        self.last_load_status = self._build_status(connections, tools, errors)
        self._publish_load_status()
        return tools

    @staticmethod
    def _build_empty_status() -> dict[str, Any]:
        """Constrói um snapshot vazio — sem servidores, sem tools."""
        return {
            "loaded_at": datetime.now(UTC).isoformat(),
            "servers": {},
            "tools_by_name": {},
        }

    @staticmethod
    def _build_status(
        connections: dict[str, Any],
        tools: list[BaseTool],
        errors: list[McpServerConnectionError],
    ) -> dict[str, Any]:
        """Constrói o snapshot de estado a partir do resultado de
        `list_mcp_tools(connections)`.

        Status por servidor:
        - `configured=True, connected=True, tool_count=N, last_error=None` quando
          o servidor conectou e expôs N tools.
        - `configured=True, connected=False, tool_count=0, last_error=<sanitized>`
          quando o servidor falhou (mensagem do erro passa por `redact_credentials`
          para defender a REQ-007).

        `tools_by_name` mapeia cada nome qualificado (`mcp__<server>__<tool>`)
        ao seu servidor de origem — usado pelo `McpToolAvailabilityMiddleware`
        pra detectar chamadas a tools que deveriam estar no set mas não estão.
        """
        server_status: dict[str, dict[str, Any]] = {}
        tools_by_name: dict[str, str] = {}

        # Conecta cada servidor a seu status. Servidores SEM erro em `errors`
        # estão conectados; servidores COM erro estão desconectados.
        connected_failed = {err.server_name: err for err in errors}

        # Conta tools por servidor (qualificados).
        for tool in tools:
            tools_by_name[tool.name] = _server_of(tool.name, connections)

        tool_counts: dict[str, int] = {}
        for qname, server_name in tools_by_name.items():
            tool_counts[server_name] = tool_counts.get(server_name, 0) + 1

        for server_name in connections:
            if server_name in connected_failed:
                err = connected_failed[server_name]
                server_status[server_name] = {
                    "configured": True,
                    "connected": False,
                    "tool_count": 0,
                    "last_error": redact_credentials(err),
                }
            else:
                server_status[server_name] = {
                    "configured": True,
                    "connected": True,
                    "tool_count": tool_counts.get(server_name, 0),
                    "last_error": None,
                }

        return {
            "loaded_at": datetime.now(UTC).isoformat(),
            "servers": server_status,
            "tools_by_name": tools_by_name,
        }

    def _load_mcp_tools(self) -> list[BaseTool]:
        """Versão síncrona de `_aload_mcp_tools`, para `wrap_model_call`.

        `_aload_mcp_tools` é async — precisa rodar num event loop. Como
        `wrap_model_call` é síncrono, sempre usa `asyncio.run` para criar
        um loop temporário.
        """
        try:
            return asyncio.run(self._aload_mcp_tools())
        except RuntimeError as e:
            if "already running" in str(e):
                # Loop já rodando — não deveria acontecer em sync path,
                # mas se acontecer, devolve vazio e loga o erro.
                _audit_log.error(
                    "mcp_tools_middleware event=sync_in_async_context "
                    "error=cannot_run_async_in_sync_wrapper"
                )
                self.connection_errors = []
                self._loaded_tools = {}
                self.last_load_status = self._build_empty_status()
                self._publish_load_status()
                return []
            raise
        except Exception as exc:  # noqa: BLE001 — REQ-004: falha de resolução/config não pode travar o agente
            _audit_log.error(
                "mcp_tools_middleware event=config_load_failed error=%s",
                str(exc),
                exc_info=True,
            )
            self.connection_errors = []
            self._loaded_tools = {}
            self.last_load_status = self._build_empty_status()
            self._publish_load_status()
            return []

    def _publish_load_status(self) -> None:
        """Copia `last_load_status` para o `McpToolAvailabilityMiddleware` ativo.

        Sem este push, o nó `tools` categoriza toda call `mcp__*` como
        `not_configured` mesmo quando o nó `model` acabou de carregar as
        tools com sucesso (bug observado com zernio em produção).
        """
        try:
            from src.agents.unified.mcp_tool_availability import (
                McpToolAvailabilityMiddleware,
            )
        except ImportError:  # pragma: no cover
            return
        availability = McpToolAvailabilityMiddleware.get_latest()
        if availability is not None:
            availability.last_load_status = self.last_load_status

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
        try:
            mcp_tools = await self._aload_mcp_tools()
        except Exception as exc:  # noqa: BLE001 — REQ-004: falha de resolução/config não pode travar o agente
            _audit_log.error(
                "mcp_tools_middleware event=config_load_failed error=%s",
                str(exc),
                exc_info=True,
            )
            self.connection_errors = []
            self._loaded_tools = {}
            self.last_load_status = self._build_empty_status()
            self._publish_load_status()
            return await handler(request)

        combined = list(request.tools or []) + mcp_tools
        return await handler(request.override(tools=combined))

    def _inject_loaded_tool(self, request: ToolCallRequest) -> ToolCallRequest:
        """Anexa a BaseTool MCP em `request.tool` quando o ToolNode não a tem.

        O ToolNode só registra tools estáticas do grafo. Tools MCP entram
        via `wrap_model_call` (visíveis ao modelo) mas `request.tool` chega
        `None` na execução. Sem esta injeção, `execute()` cai em
        `_validate_tool_call` → "is not a valid tool".
        """
        if request.tool is not None:
            return request
        tool_name = request.tool_call.get("name", "")
        mcp_tool = self._loaded_tools.get(tool_name)
        if mcp_tool is None:
            return request
        return request.override(tool=mcp_tool)

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Any],
    ) -> Any:
        """Injeta a tool MCP carregada e delega (envelope/availability/execute)."""
        return handler(self._inject_loaded_tool(request))

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Any],
    ) -> Any:
        """Versão async de `wrap_tool_call` — obrigatória em produção."""
        return await handler(self._inject_loaded_tool(request))


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


# --------------------------------------------------------------------------- #
# Helpers para o snapshot `last_load_status` e sanitização de erros
# --------------------------------------------------------------------------- #
# Patterns que comumente armazenam credenciais em mensagens de erro de clientes
# HTTP / MCP. Defesa em profundidade contra o vetor "vendor exception vazou
# header com credencial" — REQ-007 do `mcp-client` (`no credential leak`).
#
# Cada regex casa `<header-key> <sep> <secret>` (onde `<sep>` é `:`, `=`, ou
# espaço). O `<secret>` é um valor opaco com pelo menos 8 chars (heurística
# simples — evita redaction falso-positiva em strings curtas como hashes de
# protocolo).
_REDACT_PATTERNS: tuple[re.Pattern[str], ...] = (
    # Authorization: Bearer <token>  /  X-Authorization: <token>
    # (cabe qualquer header cuja última palavra contida seja "authorization"
    # — cobre X-Internal-Authorization, X-Custom-Auth-Authorization, etc.).
    # Casa o bloco INTEIRO (header key + sep + valor) e substitui por
    # `<credential-redacted>` — não manteremos NEM o nome do header, porque
    # REQ-007 do `mcp-client` proíbe QUALQUER string de `env`/`headers`
    # em mensagens de erro (a chave também pode revelar qual serviço está
    # sendo acessado).
    re.compile(
        r"(?im)(?:[A-Za-z_][A-Za-z0-9_]*[-_]?)?[Aa]uthorization"
        r"\s*[:=]\s*[A-Za-z0-9._+/\-]{8,}"
    ),
    # Bearer <token> standalone (sem header key antes)
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]{8,}"),
    # Basic <base64>
    re.compile(r"(?i)\bbasic\s+[A-Za-z0-9+/=]{8,}"),
    # api_key= / api-key= / API_KEY:
    re.compile(
        r"(?i)\bapi[_-]?key\s*[:=]\s*[A-Za-z0-9._\-]{8,}"
    ),
    # secret= / SECRET:
    re.compile(r"(?i)\bsecret\s*[:=]\s*[A-Za-z0-9._\-]{8,}"),
    # token= / TOKEN:
    re.compile(r"(?i)\btoken\s*[:=]\s*[A-Za-z0-9._\-]{8,}"),
    # password= / PASSWORD:
    re.compile(r"(?i)\bpassword\s*[:=]\s*\S{8,}"),
)


def redact_credentials(err: McpServerConnectionError) -> str:
    """Devolve uma string do erro de conexão **sem credenciais**.

    O `McpServerConnectionError` é construído com uma mensagem arbitrária
    vinda do cliente MCP upstream. Se essa mensagem incluir valores que
    pareçam credenciais (regex conservador — não é o objetivo logar 100%
    dos casos, é defender contra os óbvios), o par `<key> <sep> <value>` é
    INTEIRAMENTE substituído por `<credential-redacted>` — incluindo o nome
    do header, porque ele pode revelar qual serviço está sendo acessado
    (ex.: `X-Stripe-API-Key` revela Stripe). Mesmo o agent não recebe o
    nome do header neste caminho de erro.

    Usado para preencher `last_load_status.servers[name].last_error` e o
    log estruturado `_audit_log`. Defesa em profundidade — REQ-007 do
    `mcp-client` (proíbe QUALQUER string de `env`/`headers` em mensagens
    de erro expostas ao modelo).
    """
    raw = str(err)
    redacted = raw
    for pattern in _REDACT_PATTERNS:
        redacted = pattern.sub("<credential-redacted>", redacted)
    return (
        f"{type(err).__name__}: {redacted}"
        if redacted
        else type(err).__name__
    )


def _server_of(qualified_name: str, connections: dict[str, Any]) -> str:
    """Inferência simples do servidor de origem a partir do nome qualificado.

    O `MultiServerMCPClient` qualifica ferramentas como `mcp__<server>__<tool>`
    (após a re-qualificação em `_qualify_tool_names`). Quando o nome está fora
    desse padrão (ex.: ferramenta upstream mal-comportada que retornou nome
    cru), inferimos a partir do `connections` disponível — primeiro servidor
    configurado é a heurística fraca já usada pelo `_qualify_tool_names`.
    """
    if qualified_name.startswith("mcp__"):
        parts = qualified_name.split("__", 2)
        if len(parts) == 3:
            return parts[1]
    if connections:
        first_server = next(iter(connections))
        return str(first_server)
    return "unknown"


__all__ = ["McpToolsMiddleware"]    
