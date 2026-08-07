"""`McpToolAvailabilityMiddleware` — intercepta `wrap_tool_call` para tool
calls com prefixo `mcp__*` cuja tool **NÃO está** no set model-bound e
devolve um `ToolMessage(status="error", content=<categorizado>)`.

Caso da change `fix-mcp-tool-not-exposed-error` (Decision 2 do design):
o `langgraph.prebuilt.tool_node.ToolNode._validate_tool_call` emite
`"Error: <tool> is not a valid tool, try one of [...]"` quando recebe
uma `ToolCall` com nome ausente de `tools_by_name`. Esse erro é genérico
e confunde o agente — perde a oportunidade de dizer "o servidor
`zernio` não está configurado" vs. "está configurado mas caiu" vs.
"está OK mas você digitou o nome errado".

Este middleware roda ENTRE o `EnvelopeMiddleware` (mais próximo do modelo)
e o `McpToolsMiddleware` (mais perto da borda) na pilha do deepagents.
Ordem em `agent.py`:
```python
middleware=[
    McpToolsMiddleware(),       # injeta tools MCP no set
    McpToolAvailabilityMiddleware(),  # <-- este
    EnvelopeMiddleware(),       # filtra pelo envelope
]
```

## Categorias

| Categoria | Quando | Conteúdo do ToolMessage |
|---|---|---|
| `not_configured` (Task 3) | server_name ausente de `last_load_status.servers` (usuário não tem o servidor) | inclui server_name + sugestão "configure via API admin" |
| `not_connected` (Task 4) | server_name presente em `servers` com `connected=False` | inclui server_name + `last_error` sanitizado (Task 4 incluiu regex adicional pegando env vars UPPERCASE) |
| `unknown_tool_name` (Task 5) | server conectado, tool_name NÃO em `tools_by_name` | lista as tools REAIS do servidor + substring compat do langgraph `is not a valid tool` |
| `filtered_by_envelope` (Task 5) | tool em `tools_by_name` MAS NÃO em `model_bound_tools` (envelope cortou) | explica "existe no servidor mas não foi concedida pra esta conversa" |

**Sinal opcional `model_bound_tools`:** o middleware só consegue
distinguir `filtered_by_envelope` de `not_applicable` se o caller
(integrador do grafo) popular `last_load_status["model_bound_tools"]`
com o `set` de qualifiers que efetivamente chegaram ao modelo. Sem
isso, `unknown_tool_name` é o fallback conservador — não
intercepção indevida.

## Não-objetivos

- **Não** intercepta tool calls nativas (sem prefixo `mcp__`) — passa direto.
- **Não** filtra nem classifica permissões — isso é responsabilidade do
  `EnvelopeMiddleware`. Esta camada é sobre diagnóstico de "tool ausente
  do set".
- **Não** substitui `INVALID_TOOL_NAME_ERROR_TEMPLATE` do langgraph vendor —
  só intercepta ANTES do `ToolNode._validate_tool_call` ser alcançado.
"""
from __future__ import annotations

import logging
import re
from collections.abc import Callable
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ToolCallRequest
from langchain_core.messages import ToolMessage

_audit_log = logging.getLogger("jeff_ai.mcp_tool_availability")

_MCP_PREFIX = "mcp__"
_SERVER_NAME_PARSE_ERROR = "unknown"

# Sanitização defensiva do LADO DO CONSUMIDOR do `last_error`. Mesmo o
# `McpToolsMiddleware` (Task 2) já aplicando `redact_credentials` na hora
# de popular `last_load_status`, este middleware **re-sanitiza** antes de
# exibir — defesa em profundidade contra (a) callers que escrevem
# `last_load_status` diretamente sem passar pelo `McpToolsMiddleware`,
# ou (b) versões futuras que mudem a sanitização. Mesmas regras do
# `redact_credentials` original — mantidas AQUI (não importadas) para
# evitar acoplamento entre os dois módulos de middleware.
_REDACT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"(?im)(?:[A-Za-z_][A-Za-z0-9_]*[-_]?)?[Aa]uthorization"
        r"\s*[:=]\s*[A-Za-z0-9._+/\-]{8,}"
    ),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]{8,}"),
    re.compile(r"(?i)\bbasic\s+[A-Za-z0-9+/=]{8,}"),
    re.compile(r"(?i)\bapi[_-]?key\s*[:=]\s*[A-Za-z0-9._\-]{8,}"),
    re.compile(r"(?i)\bsecret\s*[:=]\s*[A-Za-z0-9._\-]{8,}"),
    re.compile(r"(?i)\btoken\s*[:=]\s*[A-Za-z0-9._\-]{8,}"),
    re.compile(r"(?i)\bpassword\s*[:=]\s*\S{8,}"),
    # Qualquer palavra em MAIÚSCULAS com `_` (estilo `MY_API_KEY`, `ZERNIO_API_KEY`)
    # seguida de `=` ou `:` e um valor opaco. Pega nomes de env vars em
    # log message / stack trace — REQ-007 do `mcp-client` exige que
    # NEM A KEY nem o valor vaze.
    re.compile(
        r"(?i)\b[A-Z][A-Z0-9_]{3,}\s*[:=]\s*[A-Za-z0-9._\-]{8,}"
    ),
)


def _sanitize_error_text(raw: str) -> str:
    """Versão string-input do `redact_credentials` do `McpToolsMiddleware`
    — útil quando o `last_error` chega pré-formatado (não como
    `McpServerConnectionError`, ex.: em testes que injetam `last_error`
    diretamente)."""
    redacted = raw
    for pattern in _REDACT_PATTERNS:
        redacted = pattern.sub("<credential-redacted>", redacted)
    return redacted


_LATEST_AVAILABILITY: "McpToolAvailabilityMiddleware | None" = None


class McpToolAvailabilityMiddleware(AgentMiddleware[Any, Any, Any]):
    """Intercepta tool calls `mcp__*` ausentes do set e devolve diagnóstico
    categorizado.

    O atributo `last_load_status` é publicado pelo `McpToolsMiddleware`
    (Decision 3) após cada `awrap_model_call` — então no momento em
    que `awrap_tool_call` é chamado, o estado já reflete o carregamento
    daquela request. Em runtime o snapshot também é lido de
    `McpToolsMiddleware.get_latest()` se o push ainda não tiver ocorrido
    (defesa contra ordem de instanciação / hot-reload do grafo).

    Attributes
    ----------
    last_load_status:
        Snapshot serializável do estado dos servidores MCP no início desta
        chamada de modelo — mesmo shape do `McpToolsMiddleware.last_load_status`
        (`{servers: {name: ...}, tools_by_name: {qualified: server}}`).
        Quem compõe o grafo é responsável por copiar/injetar este valor
        antes do dispatch de tools — por padrão começa vazio, o que
        equivale a "nenhum servidor configurado para esta sessão" (e
        dispara `not_configured` em qualquer tool call `mcp__*`, que é
        a categoria mais defensiva).
    """

    def __init__(self) -> None:
        super().__init__()
        # Mesmo shape do `McpToolsMiddleware.last_load_status` (Decision 3).
        # Preenchido por `McpToolsMiddleware._publish_load_status` após cada
        # load; começando vazio, qualquer tool call `mcp__*` cai em
        # `not_configured` até o primeiro model call publicar o snapshot.
        self.last_load_status: dict[str, Any] = {}
        global _LATEST_AVAILABILITY
        _LATEST_AVAILABILITY = self

    @classmethod
    def get_latest(cls) -> "McpToolAvailabilityMiddleware | None":
        """Devolve a instância registrada mais recentemente, ou `None`."""
        return _LATEST_AVAILABILITY

    def _effective_load_status(self) -> dict[str, Any]:
        """Snapshot efetivo para categorizar tool calls.

        Preferência:
        1. `self.last_load_status` se já tiver sido publicado/injetado
           (presença da chave `servers` — setada por
           `McpToolsMiddleware._publish_load_status` ou por testes).
        2. Snapshot do `McpToolsMiddleware.get_latest()` (fonte da verdade
           do último model call), se existir.
        3. `self.last_load_status` (pode estar `{}` → `not_configured`).
        """
        if "servers" in self.last_load_status:
            return self.last_load_status
        try:
            from src.agents.unified.mcp_tools_middleware import McpToolsMiddleware
        except ImportError:  # pragma: no cover — mesmo pacote
            return self.last_load_status
        latest = McpToolsMiddleware.get_latest()
        if latest is not None and "servers" in latest.last_load_status:
            return latest.last_load_status
        return self.last_load_status

    # -------------------------------------------------------------- #
    # Helpers de categorização
    # -------------------------------------------------------------- #
    @staticmethod
    def _parse_server(tool_name: str) -> str:
        """Extrai `server_name` de `mcp__<server>__<tool>`. Se mal-formado,
        retorna `unknown` — caller trata como `not_configured`."""
        if not tool_name.startswith(_MCP_PREFIX):
            return _SERVER_NAME_PARSE_ERROR
        # Esperado: `mcp__<server>__<tool>` — 3 partes após split por `__`
        parts = tool_name.split("__", 2)
        if len(parts) != 3 or not parts[1]:
            return _SERVER_NAME_PARSE_ERROR
        return parts[1]

    def _categorize(self, tool_name: str) -> tuple[str, str]:
        """Devolve `(categoria, server_name)` para uma tool call
        `mcp__<server>__<tool>` cuja tool NÃO está no set entregue ao
        modelo.

        Categorias (na ordem de checagem):
        - `not_configured` (Task 3): server_name ausente de `servers`.
        - `not_connected` (Task 4): server_name em `servers` com
          `connected=False`.
        - `filtered_by_envelope` (Task 5): tool ESTÁ em
          `tools_by_name` mas NÃO em `model_bound_tools` (o
          `EnvelopeMiddleware` cortou do set).
        - `unknown_tool_name` (Task 5): server está conectado, tool NÃO
          está em `tools_by_name` (typo ou servidor não expõe).

        Returns:
            `(categoria, server_name)`. `categoria` ∈ {`not_configured`,
            `not_connected`, `unknown_tool_name`, `filtered_by_envelope`}.
        """
        server_name = self._parse_server(tool_name)
        status = self._effective_load_status()
        servers = status.get("servers") or {}
        tools_by_name = status.get("tools_by_name") or {}
        model_bound = status.get("model_bound_tools")

        if server_name not in servers:
            # Servidor não está configurado pra este user_id — categoria
            # mais comum, a default defensiva.
            return ("not_configured", server_name)

        # Servidor ESTÁ em `servers`. Vamos distinguir o motivo fino.
        record = servers[server_name] or {}

        if record.get("connected") is False:
            return ("not_connected", server_name)

        # Servidor conectado. Agora a pergunta fina: a tool ESTÁ em
        # `tools_by_name` (estado bruto pós-carregamento)?
        if tool_name in tools_by_name:
            # Sim — então o problema é o envelope cortando. Só temos
            # este sinal se o caller populou `model_bound_tools`
            # explicitamente (sinal opcional — default é None, que
            # significa "não sabemos o que o envelope fez"). Se
            # `model_bound_tools` é None, falhamos a categoria fina
            # e caímos em `unknown_tool_name` por segurança.
            if isinstance(model_bound, set) and tool_name not in model_bound:
                return ("filtered_by_envelope", server_name)
            # `model_bound` ausente → não conseguimos distinguir.
            # Trata como fallback conservador para `unknown_tool_name`
            # (defensivo, mas com lista real de tools mostradas).
            return ("unknown_tool_name", server_name)

        # Servidor conectado mas tool NÃO está em `tools_by_name`.
        # 99% das vezes é typo do modelo.
        return ("unknown_tool_name", server_name)

    def _format_message(
        self,
        tool_name: str,
        category: str,
        server_name: str,
        last_error: str | None = None,
    ) -> str:
        """Constrói a string de `content` do `ToolMessage` categorizado.

        Mantém o formato prefixado `[Tool '<name>' indisponível:
        <categoria>]` do design Decision 5 — assim o modelo lê um
        prefixo estável e a categoria depois. Servidor de origem, estado
        atual e sugestão acionável vêm em bullets.
        """
        server_display = (
            server_name
            if server_name != _SERVER_NAME_PARSE_ERROR
            else "<servidor não identificável>"
        )

        if category == "not_connected":
            error_display = (
                _sanitize_error_text(last_error)
                if last_error
                else "(sem detalhes do erro — verifique `list_mcp_servers_status()`)"
            )
            return (
                f"[Tool '{tool_name}' indisponível: {category}]\n"
                f"- Servidor de origem: {server_display} (do prefixo {tool_name})\n"
                "- Estado: este servidor ESTÁ configurado para o usuário, "
                "mas FALHOU ao conectar (processo offline, timeout, ou erro de auth)\n"
                f"- Erro: {error_display}\n"
                "- Sugestão: verifique se o processo do servidor está rodando "
                "e tente reconectar via API admin\n"
                "- Diagnóstico completo: chame `list_mcp_servers_status()` "
                "para inspecionar o estado atual dos MCPs em runtime"
            )

        if category == "unknown_tool_name":
            # Lista as tools que o servidor REALMENTE expôs — ajuda o
            # modelo a detectar typo. Inclui a substring do langgraph
            # vendor `is not a valid tool` para compatibilidade com
            # qualquer caller que dependa dessa string exata.
            tools_by_name = self._effective_load_status().get("tools_by_name") or {}
            real_tool_names = sorted(
                {
                    qname.split("__", 2)[-1]
                    for qname, srv in tools_by_name.items()
                    if srv == server_name
                }
            )
            real_tools_str = (
                ", ".join(real_tool_names)
                if real_tool_names
                else "(nenhuma tool exposta por este servidor)"
            )
            return (
                f"[Tool '{tool_name}' indisponível: {category}]\n"
                f"- Servidor de origem: {server_display} (do prefixo {tool_name})\n"
                "- Estado: este servidor ESTÁ conectado e EXPÕE tools, "
                f"mas '{tool_name.split('__', 2)[-1]}' não está entre elas\n"
                f"- Tools reais deste servidor: {real_tools_str}\n"
                "- Sugestão: corrija o nome da tool (typo?) para uma das "
                "tools acima; talvez seja `posts_list` em vez de "
                "`posts_create` (note o sufixo singular vs plural)\n"
                "- Mensagem original do langgraph (compat): "
                f"'Error: {tool_name} is not a valid tool, try one of "
                f"[{', '.join(real_tool_names)}].'\n"
                "- Diagnóstico completo: chame `list_mcp_servers_status()` "
                "para inspecionar o estado atual dos MCPs em runtime"
            )

        if category == "filtered_by_envelope":
            return (
                f"[Tool '{tool_name}' indisponível: {category}]\n"
                f"- Servidor de origem: {server_display} (do prefixo {tool_name})\n"
                "- Estado: esta tool EXISTE no servidor "
                f"'{server_display}' e está anunciada, mas foi REMOVIDA "
                "pelo envelope de permissões desta tarefa\n"
                "- Diferença deste erro vs. erro genérico de "
                "permission denial: a diferença é que esta tool "
                "existe e está disponível — só não foi concedida pra "
                "esta conversa. Se o usuário quiser usá-la, precisa "
                "solicitar que o envelope conceda a capability "
                "necessária\n"
                "- Diagnóstico completo: chame `list_mcp_servers_status()` "
                "para inspecionar o estado atual dos MCPs em runtime"
            )

        # not_configured (default categórico)
        return (
            f"[Tool '{tool_name}' indisponível: {category}]\n"
            f"- Servidor de origem: {server_display} (do prefixo {tool_name})\n"
            "- Estado: este servidor NÃO está configurado para o "
            "usuário desta sessão em `user_mcp_servers`\n"
            "- Sugestão: adicione-o via API admin de servidores "
            "MCP deste Jeff AI\n"
            "- Diagnóstico completo: chame "
            "`list_mcp_servers_status()` para inspecionar o estado "
            "atual dos MCPs em runtime"
        )

    # -------------------------------------------------------------- #
    # Hooks (sync + async — espelhando o que o EnvelopeMiddleware faz)
    # -------------------------------------------------------------- #
    def _evaluate_tool_call(
        self, request: ToolCallRequest
    ) -> ToolMessage | None:
        """Núcleo compartilhado de `wrap_tool_call`/`awrap_tool_call`.

        Returns:
            `None` se a tool deve passar (`handler(request)`); `ToolMessage`
            com `status="error"` categorizado caso contrário. Caller NÃO
            deve chamar `handler` quando recebe um `ToolMessage` (mesma
            disciplina do `EnvelopeMiddleware._evaluate_tool_call`).
        """
        tool_name = request.tool_call.get("name", "")
        tool_call_id = request.tool_call.get("id", "")

        # Pass-through 1: tool nativa (sem prefixo `mcp__`). Mesmo que a
        # categorização estivesse errada, não nos metemos com tools nativas.
        if not tool_name.startswith(_MCP_PREFIX):
            return None

        # Pass-through 2: tool `mcp__*` MAS tanto em `tools_by_name`
        # (anunciada pelo MCP) QUANTO em `model_bound_tools` (a mesma
        # string foi entregue ao modelo após o filtro do envelope).
        # Se `model_bound_tools` for None, caímos no caminho "não
        # sabemos" → a ferramenta pode estar em `tools_by_name` (e
        # chegou ao modelo) ou pode ter sido cortada pelo envelope.
        # A heurística conservadora: se está em `tools_by_name` E não
        # temos `model_bound_tools` definido, **passa** (assume que
        # chegou — comportamento seguro default; a categoria fina
        # nesse caso não importa para o agente).
        #
        # Task 5 (atual) — se `model_bound_tools` foi populado,
        # podemos DISTINGUIR `filtered_by_envelope` (tool em
        # `tools_by_name` mas NÃO em `model_bound_tools`) da
        # não-intercepção (tool em ambos).
        status = self._effective_load_status()
        tools_by_name = status.get("tools_by_name") or {}
        model_bound = status.get("model_bound_tools")
        if tool_name in tools_by_name:
            if model_bound is None or tool_name in model_bound:
                # Sem info do envelope → assume que a tool chegou ao modelo.
                # Com `model_bound_tools` populado → tool de fato chegou.
                return None

        # Intercepta: tool `mcp__*` ausente do set entregue ao modelo.
        category, server_name = self._categorize(tool_name)

        # Para `not_connected`, busca o `last_error` do servidor em
        # `last_load_status.servers[server_name].last_error`. Esse valor já
        # foi sanitizado pelo `redact_credentials` em `McpToolsMiddleware`
        # (Task 2) — mas re-sanitizamos em `_format_message` por defesa.
        last_error: str | None = None
        if category == "not_connected":
            server_record = (status.get("servers") or {}).get(server_name) or {}
            err = server_record.get("last_error")
            last_error = err if isinstance(err, str) else None

        content = self._format_message(
            tool_name, category, server_name, last_error=last_error
        )

        _audit_log.info(
            "mcp_tool_availability event=intercept tool=%r category=%r server=%r",
            tool_name,
            category,
            server_name,
        )
        return ToolMessage(
            content=content,
            name=tool_name,
            tool_call_id=tool_call_id,
            status="error",
        )

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Any],
    ) -> Any:
        """Versão síncrona (espelha o `EnvelopeMiddleware.wrap_tool_call`)."""
        blocked = self._evaluate_tool_call(request)
        if blocked is not None:
            return blocked
        return handler(request)

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Any],
    ) -> Any:
        """Versão assíncrona — obrigatória em produção (mesma razão do
        `EnvelopeMiddleware.awrap_tool_call`: o `langgraph-api` roda
        via `astream()`/`ainvoke()` e o langchain 1.x não faz bridge
        automático de sync→async em middleware)."""
        blocked = self._evaluate_tool_call(request)
        if blocked is not None:
            return blocked
        return await handler(request)


__all__ = ["McpToolAvailabilityMiddleware"]
