"""Teste de paridade de tools entre canais (change `wire-scheduling-tools-to-agent`).

Cobre REQ-014 cenário 1 do spec `task-scheduling`: a única variação de tool
set entre sessões é por servidor MCP configurado por usuário
(`user_mcp_servers`), nunca por canal (web vs WhatsApp vs Telegram).

A trava de regressão: ambos os pontos de entrada do grafo (`unified` na
plataforma LangGraph para web; `LangGraphDirectAgentRunner` para WhatsApp e
Telegram) passam pela MESMA fábrica `build_unified()`. Se um canal passar
a filtrar tools nativas, este teste pega.

Por que `test_tools_registered_in_unified_graph` (em `test_scheduling_tools.py`)
não basta: ele confirma que o nome está em `_TOOL_NAMES` (lista já congelada
no import do módulo), mas NÃO prova que o `build_unified()` chamado pelo
plataforma LangGraph (entrypoint web) recebe o MESMO set que o chamado pelo
`LangGraphDirectAgentRunner` (entrypoint WhatsApp/Telegram). É exatamente o
delta que esta change traz: garantir que todos os canais veem o mesmo set.

Spy: `create_deep_agent` é mockado para capturar os kwargs sem precisar
do LLM/Postgres/AsyncStore reais (mesmo padrão de
`test_build_unified_parametrization.py`). Comparamos as listas de tools
entre duas chamadas de `build_unified()` — sem args (plataforma LangGraph)
e com checkpointer+store (`LangGraphDirectAgentRunner`).
"""
from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from src.agents.unified import agent as agent_module
from src.agents.unified.agent import (
    _SYSTEM_PROMPT,
    _TOOL_NAMES,
    _UNIFIED_TOOLS,
    build_unified,
)


class _FakeCompiledGraph:
    """Stand-in para o retorno de `create_deep_agent`.

    Igual ao de `test_build_unified_parametrization.py` — só precisa
    aceitar `.with_config(...)` igual ao `CompiledStateGraph` real.
    """

    def with_config(self, _config: Any) -> "_FakeCompiledGraph":
        return self


def _capture_build_unified_kwargs(**call_kwargs: Any) -> dict[str, Any]:
    """Roda `build_unified(**call_kwargs)` capturando o que chega em
    `create_deep_agent`. Retorna o dict de kwargs observado."""
    with patch.object(
        agent_module,
        "create_deep_agent",
        side_effect=lambda **_kwargs: _FakeCompiledGraph(),
    ) as spy:
        build_unified(**call_kwargs)
        assert spy.call_count == 1
        return spy.call_args.kwargs


def _tool_names_from_kwargs(kwargs: dict[str, Any]) -> list[str]:
    """Extrai os NOMES das tools de um kwargs de `create_deep_agent`.

    O `kwargs["tools"]` é a lista literal de ferramentas (mesma instância
    de `_UNIFIED_TOOLS` se nada foi filtrado). O teste converte para a
    forma de `list[str]` (pelo `.name` ou `.__name__`) para comparar
    independentemente de identidade de objeto — duas chamadas produzem a
    mesma lista porque vêm do mesmo módulo.
    """
    tools = kwargs.get("tools") or []
    return [getattr(t, "name", None) or getattr(t, "__name__", "") for t in tools]


def test_build_unified_web_path_receives_full_tool_set_including_scheduling() -> None:
    """Cenário 1/REQ-014: a chamada de `build_unified()` sem argumentos (o
    que a plataforma LangGraph faz para o entrypoint web) recebe a lista
    completa de tools — incluindo as 3 de agendamento."""
    kwargs = _capture_build_unified_kwargs()

    tool_names = _tool_names_from_kwargs(kwargs)
    for name in (
        "create_scheduled_task",
        "list_scheduled_tasks",
        "cancel_scheduled_task",
    ):
        assert name in tool_names, (
            f"web channel: {name} ausente do tool set recebido por create_deep_agent"
        )


def test_build_unified_direct_runner_path_receives_same_tool_set_as_web() -> None:
    """Cenário 1/REQ-014: a chamada de `build_unified(checkpointer=...,
    store=...)` (o que `LangGraphDirectAgentRunner` faz para WhatsApp e
    Telegram) recebe o MESMO set de tools que a chamada sem args
    (entrypoint web). A comparação é por conteúdo — duas listas
    idênticas módulo-a-módulo, mas queremos travar contra qualquer
    filtragem por canal que alguém possa introduzir."""
    web_kwargs = _capture_build_unified_kwargs()
    direct_runner_kwargs = _capture_build_unified_kwargs(
        checkpointer=object(),
        store=object(),
    )

    web_tool_names = sorted(_tool_names_from_kwargs(web_kwargs))
    direct_tool_names = sorted(_tool_names_from_kwargs(direct_runner_kwargs))

    assert web_tool_names == direct_tool_names, (
        "Os dois canais devem ver o mesmo tool set. "
        f"Diff: web={set(web_tool_names) - set(direct_tool_names)}, "
        f"direct={set(direct_tool_names) - set(web_tool_names)}"
    )
    # As 3 de agendamento presentes em ambos.
    for name in (
        "create_scheduled_task",
        "list_scheduled_tasks",
        "cancel_scheduled_task",
    ):
        assert name in direct_tool_names, (
            f"WhatsApp/Telegram (LangGraphDirectAgentRunner): {name} "
            "ausente do tool set — REQ-014 violado."
        )


def test_build_unified_web_and_direct_runner_share_system_prompt_and_interrupt_on() -> None:
    """Cenário 1/REQ-014: além do tool set, o `system_prompt` e o
    `interrupt_on` (derivado das tools reais via `build_interrupt_on`) são
    os mesmos nos dois canais. Prova a paridade completa do grafo entre
    web e WhatsApp/Telegram.

    `interrupt_on` é construído uma vez no import de `agent.py` a partir
    de `_TOOL_NAMES` — então ambos os call sites vão usar a mesma
    instância. Aqui comparamos o conteúdo para travar mudanças
    acidentais."""
    web_kwargs = _capture_build_unified_kwargs()
    direct_runner_kwargs = _capture_build_unified_kwargs(
        checkpointer=object(),
        store=object(),
    )

    assert web_kwargs.get("system_prompt") == direct_runner_kwargs.get("system_prompt")
    # `_SYSTEM_PROMPT` é o system_prompt passado pelos dois caminhos
    # (mesma referência global no módulo).
    assert web_kwargs.get("system_prompt") == _SYSTEM_PROMPT
    # `interrupt_on` é a mesma referência — congelada no import de
    # `agent.py` a partir de `_TOOL_NAMES`.
    assert web_kwargs.get("interrupt_on") == direct_runner_kwargs.get("interrupt_on")


def test_scheduling_tools_present_in_unified_tools_module_attribute() -> None:
    """Sanity: `_UNIFIED_TOOLS` (a lista de ferramentas registrada no
    grafo unificado no momento do import) já contém as 3 tools de
    agendamento. Garante que a paridade testada acima está embasada numa
    lista-base que DE FATO contém as tools."""
    tool_names = [
        getattr(t, "name", None) or getattr(t, "__name__", "")
        for t in _UNIFIED_TOOLS
    ]
    for name in (
        "create_scheduled_task",
        "list_scheduled_tasks",
        "cancel_scheduled_task",
    ):
        assert name in tool_names
        assert name in _TOOL_NAMES
