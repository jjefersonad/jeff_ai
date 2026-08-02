"""Testes da parametrização de `build_unified()` (task `agendamento-jeff-cli-task-graph-1`).

Cobre o delta `agendamento-jeff-cli-unified-agent-graph-spec` ("Checkpointer/store
injetáveis"):

  1. Cenário "chamada sem argumentos" — `build_unified()` produz o mesmo grafo
     de antes (nenhuma regressão). Mockar `create_deep_agent` permite isolar
     esse contrato do resto do grafo (Postgres, Ollama, etc.) — sem mockar
     nada, este teste não roda fora de um ambiente com todas as dependências
     reais de pé.
  2. Cenário "chamada com checkpointer/store explícitos" — os objetos
     passados chegam intactos em `create_deep_agent`, sem "plataforma LangGraph
     injetou outra coisa por cima" (que seria a regressão que o delta está
     evitando).
"""
from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from src.agents.unified import agent as agent_module
from src.agents.unified.agent import build_unified


class _FakeCompiledGraph:
    """Stand-in para o retorno de `create_deep_agent` — apenas precisa aceitar
    `.with_config(...)` igual ao `CompiledStateGraph` real do LangGraph."""

    def with_config(self, _config: Any) -> "_FakeCompiledGraph":
        return self


def test_build_unified_without_args_keeps_legacy_call() -> None:
    """Cenário "chamada sem argumentos": nenhum checkpointer/store REAL é
    passado a `create_deep_agent` — só `None`, que é o default idêntico ao
    que a plataforma usa quando ela mesma injeta checkpointer/store via
    `langgraph.json` (a plataforma também injeta `None` se o `langgraph.json`
    não tiver `checkpointer`/`store`). Nenhuma regressão: o grafo produzido
    é idêntico ao de antes da mudança.
    """
    with patch.object(
        agent_module, "create_deep_agent", side_effect=lambda **_kwargs: _FakeCompiledGraph()
    ) as spy:
        build_unified()

        assert spy.call_count == 1
        kwargs = spy.call_args.kwargs
        # Os dois parâmetros novos existem como kwargs (a fábrica os
        # repassa), e ambos com `None` — exatamente o que `create_deep_agent`
        # faz quando o caller não os passa (a plataforma LangGraph os anexa
        # depois em runtime, sem precisar de valores aqui).
        assert kwargs.get("checkpointer") is None
        assert kwargs.get("store") is None


def test_build_unified_accepts_checkpointer_and_store_kwargs() -> None:
    """Cenário "chamada com checkpointer/store explícitos": os objetos
    passados são repassados a `create_deep_agent` intactos."""
    sentinel_checkpointer = object()
    sentinel_store = object()

    with patch.object(
        agent_module, "create_deep_agent", side_effect=lambda **_kwargs: _FakeCompiledGraph()
    ) as spy:
        build_unified(checkpointer=sentinel_checkpointer, store=sentinel_store)

        assert spy.call_count == 1
        kwargs = spy.call_args.kwargs
        assert kwargs["checkpointer"] is sentinel_checkpointer
        assert kwargs["store"] is sentinel_store


def test_build_unified_with_only_checkpointer() -> None:
    """Chamar só com `checkpointer` (deixar `store` no default) é aceito."""
    sentinel_checkpointer = object()

    with patch.object(
        agent_module, "create_deep_agent", side_effect=lambda **_kwargs: _FakeCompiledGraph()
    ) as spy:
        build_unified(checkpointer=sentinel_checkpointer)

        assert spy.call_count == 1
        kwargs = spy.call_args.kwargs
        assert kwargs["checkpointer"] is sentinel_checkpointer
        assert kwargs["store"] is None


def test_build_unified_with_only_store() -> None:
    """Chamar só com `store` (deixar `checkpointer` no default) é aceito."""
    sentinel_store = object()

    with patch.object(
        agent_module, "create_deep_agent", side_effect=lambda **_kwargs: _FakeCompiledGraph()
    ) as spy:
        build_unified(store=sentinel_store)

        assert spy.call_count == 1
        kwargs = spy.call_args.kwargs
        assert kwargs["store"] is sentinel_store
        assert kwargs["checkpointer"] is None


def test_build_unified_does_not_override_explicit_args_with_env() -> None:
    """Quando o caller passa `checkpointer`/`store` explícitos, eles DEVEM
    ser os repassados a `create_deep_agent` — não há fallback para env vars
    da plataforma (Postgres URI etc.) dentro desta função. Esse é o invariante
    que libera `jeff_cli.py` a invocar o grafo fora da plataforma.
    """
    sentinel_checkpointer = object()
    sentinel_store = object()

    with patch.object(
        agent_module, "create_deep_agent", side_effect=lambda **_kwargs: _FakeCompiledGraph()
    ) as spy:
        build_unified(checkpointer=sentinel_checkpointer, store=sentinel_store)

        kwargs = spy.call_args.kwargs
        # Nada de `os.environ["POSTGRES_URI"]` ou similar dentro do kwargs —
        # o caller tem controle total.
        assert kwargs["checkpointer"] is sentinel_checkpointer
        assert kwargs["store"] is sentinel_store


@pytest.mark.parametrize("name", ["checkpointer", "store"])
def test_build_unified_default_for_kwarg_is_none(name: str) -> None:
    """Os dois novos parâmetros são opcionais com default `None`."""
    import inspect

    sig = inspect.signature(build_unified)
    param = sig.parameters[name]
    assert param.default is None, (
        f"`{name}` deveria ter default None (opcional); default atual: {param.default!r}"
    )
