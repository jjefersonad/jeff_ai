"""Rotas do `CompositeBackend` do grafo `unified`.

Trava a correção da task `unified-agent-realignment-task-floor-2`: a rota
`/memories/` era condicionada ao "modo" do grafo (`include_store=
_select_include_store(mode)`). Como o sistema de modos nunca existiu de fato,
tudo era construído como `chat` — e `chat` não estava na lista de modos que
"precisavam" de memória. Resultado: a rota ficava desmontada em TODOS os grafos.

NOTA: isso não é o mesmo que "a memória estava desligada". As tools
`save_memory` / `search_memory` usam `get_store()` (o Store do LangGraph,
injetado pelo runtime via `langgraph.json`) e sempre funcionaram,
independentemente daqui. O que faltava era o acesso *filesystem* à memória.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from deepagents.backends import StoreBackend

from src.agents.unified.agent import _build_backend_factory
from src.composition.backends import MEMORIES_PREFIX


def _build_routes() -> dict:
    """Constrói o CompositeBackend fora de um runnable context do LangGraph."""
    with patch(
        "src.composition.backends.get_config",
        return_value={"configurable": {"thread_id": "test-thread"}},
    ):
        backend = _build_backend_factory()(MagicMock())
    return backend.routes


def test_memories_route_is_mounted() -> None:
    """A rota `/memories/` existe e é um StoreBackend."""
    routes = _build_routes()

    assert MEMORIES_PREFIX in routes, (
        f"rota {MEMORIES_PREFIX} ausente — o acesso filesystem à memória de "
        f"longo prazo está desmontado. Rotas: {sorted(routes)}"
    )
    assert isinstance(routes[MEMORIES_PREFIX], StoreBackend)


def test_memories_route_does_not_depend_on_mode() -> None:
    """A montagem não pode voltar a ser condicionada a modo/prompt.

    `_build_backend_factory` não aceita mais nenhum parâmetro. Se alguém
    reintroduzir um flag de modo, este teste quebra.
    """
    import inspect

    params = inspect.signature(_build_backend_factory).parameters
    assert not params, (
        "_build_backend_factory voltou a receber parâmetros "
        f"({list(params)}) — a rota /memories/ não pode ser condicional."
    )


def test_dead_mode_store_coupling_is_gone() -> None:
    """Os símbolos que acoplavam a memória ao sistema de modos não voltaram."""
    from src.agents.unified import agent as unified_agent

    for dead in ("_select_include_store", "_NEEDS_STORE_MODES"):
        assert not hasattr(unified_agent, dead), (
            f"`{dead}` voltou: a rota /memories/ está sendo condicionada a um "
            "sistema de modos que não existe."
        )
