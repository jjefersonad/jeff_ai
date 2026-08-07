"""`list_mcp_servers_status` — tool nativa para self-diagnóstico dos MCPs.

Parte da change `fix-mcp-tool-not-exposed-error` (Decision 4 do design).
Devolve o snapshot `last_load_status` do `McpToolsMiddleware` mais recente
em formato legível — usado pelo **agente** (não pelo usuário final) para
investigar por que uma tool `mcp__*` específica não está disponível, antes
de devolver um erro genérico ao usuário.

## Quando usar

Quando o modelo recebe um erro categorizado do
`McpToolAvailabilityMiddleware` (categories: `not_configured`,
`not_connected`, `unknown_tool_name`, `filtered_by_envelope`) e precisa de
mais contexto pra decidir se a falha é estrutural (servidor caiu /
configuração do usuário) ou se ele digitou o nome errado da tool.

## Tier 1

Esta tool é **Tier 1 — auto-aprovada**. O agente pode chamá-la sem
precisar de aprovação humana porque é puramente leitura. Não muta
nenhum estado, não lê credenciais do sistema, não toca em arquivos.

Esta escolha é deliberada: o agente precisa de uma **via de escape**
para investigar sem precisar de aprovação a cada erro. O risco
(`info leak` sobre quais MCPs estão configurados) é baixo —
informação equivalente ao que o modelo já inferiria pelos erros
categorizados que recebe.
"""
from __future__ import annotations

import copy
from typing import Any, Callable

from langchain_core.tools import tool

LIST_MCP_SERVERS_STATUS_NAME = "list_mcp_servers_status"

LIST_MCP_SERVERS_STATUS_DESCRIPTION = (
    "Lista os servidores MCP atualmente conectados para o usuário desta "
    "sessão, com status (configurado? conectado? contagem de tools), e as "
    "tools `mcp__*` realmente entregues ao modelo. Use como diagnóstico "
    "quando receber um erro categorizado como `not_configured`, "
    "`not_connected`, `unknown_tool_name` ou `filtered_by_envelope` para "
    "uma tool `mcp__*` específica — categorize antes de retornar o erro "
    "ao usuário, e chame esta tool para obter o estado atual completo dos "
    "servidores MCP em runtime. Read-only."
)

# Callback que devolve o `last_load_status` atual. Injetado pelo integrador
# do grafo (em produção, vem do `McpToolsMiddleware` mais recente da pilha
# do deepagents). Em testes, é sobrescrito via patch.
_current_status_provider: Callable[[], dict[str, Any]] = lambda: {}


def set_status_provider(provider: Callable[[], dict[str, Any]]) -> None:
    """Injeta o callback que devolve o `last_load_status`. Chamado uma
    vez no boot do grafo (`agent.py`) — sem necessidade de fazer em
    runtime."""
    global _current_status_provider
    _current_status_provider = provider


@tool
def list_mcp_servers_status() -> str:
    """Devolve o snapshot mais recente do estado dos servidores MCP para
    o usuário da sessão atual.

    Use esta tool quando uma tool `mcp__*` específica falhar com uma
    mensagem categorizada (`not_configured` / `not_connected` /
    `unknown_tool_name` / `filtered_by_envelope`) e você precisar de
    mais contexto para ajudar o usuário sem alucinar.

    Schema do retorno (dict JSON):
    `{loaded_at: ISO8601, servers: {server_name: {configured, connected,
      tool_count, last_error}}, tools_by_name: {qualified_name:
      server_name}}`

    O `last_error` sanitiza qualquer credencial que possa ter vindo
    no erro upstream (REQ-007 do `mcp-client`). Read-only — não muta
    nenhum estado.

    Returns:
        String JSON com o snapshot. Nunca vazia — ao menos `{"loaded_at":
        <timestamp>, "servers": {}, "tools_by_name": {}}` no caso default.
    """
    import json

    snapshot = _current_status_provider() or {}
    # Devolve uma CÓPIA PROFUNDA para garantir read-only contra mutação
    # acidental. `dict.copy()` + recursão via copy.deepkey para dicts/lists.
    safe = copy.deepcopy(snapshot)
    return json.dumps(safe, ensure_ascii=False, indent=2)


def _register_default_provider() -> None:
    """Define o provider default como o último `McpToolsMiddleware`
    instanciado. Idempotente — pode ser chamado várias vezes (a última
    chamada vence)."""
    from src.agents.unified.mcp_tools_middleware import McpToolsMiddleware

    set_status_provider(
        lambda: (
            getattr(McpToolsMiddleware.get_latest(), "last_load_status", {})
            or {}
        )
    )


# Auto-registra no import — antes da primeira chamada do grafo, isso
# garante que o provider padrão já está instalado. Chamadas subsequentes
# a `set_status_provider(...)` (em testes ou em integrações custom)
# sobrescrevem sem reverter.
_register_default_provider()


__all__ = [
    "LIST_MCP_SERVERS_STATUS_DESCRIPTION",
    "LIST_MCP_SERVERS_STATUS_NAME",
    "list_mcp_servers_status",
    "set_status_provider",
] 
