"""Ponto único de exposição dos grafos LangGraph do Jeff AI.

Os `graph_id` expostos aqui são os referenciados por `langgraph.json`,
`server.py` e pelo frontend (via `assistantId`). A injeção de adapters
nos casos de uso vive em `composition/dependencies.py`.

## Grafo unificado

O Jeff AI opera um único grafo real: `unified` (construído em
`src.agents.unified.agent`, um único system prompt, uma pilha de tools).

## `agent` / `sdd_agent` / `assistant`

Estes três IDs eram, até a task `modes-1`, "shims" que embrulhavam `unified`
via `with_mode(unified, "<modo>")` — um sistema de modos que nunca teve
efeito algum em produção (`classify_mode()` tinha zero call sites; ver
docstring de `src.agents.unified.agent`). `with_mode()` foi removido junto
com o resto do sistema de modos. Os três IDs agora são **aliases diretos**
para o mesmo objeto `unified` — o que sempre foi, na prática, o
comportamento real (todos rodavam o mesmo grafo com o mesmo prompt).

Mantidos por retrocompatibilidade com `assistantId` salvos no frontend;
`langgraph.json` continua expondo os quatro `graph_id`. **Decisão (Q5 do
design `unified-agent-realignment`, task `modes-2`): manter os três
aliases.** Custo de mantê-los é ~zero (três linhas), e removê-los quebraria
`assistantId` já salvos no `localStorage` de quem configurou o frontend
para apontar para `agent`/`sdd_agent`/`assistant` em vez de `unified`.
"""
from src.agents.unified.agent import unified

# --------------------------------------------------------------------------- #
# Aliases de retrocompatibilidade
# --------------------------------------------------------------------------- #
# Idênticos a `unified` — nunca fixaram um "modo" de verdade (ver docstring
# do módulo). `modes-2` decide se continuam existindo.
agent = unified
sdd_agent = unified
assistant = unified

__all__ = [
    "agent",
    "assistant",
    "sdd_agent",
    "unified",
]
