"""Fábrica única de `CompositeBackend` para os grafos LangGraph.

Antes, cada orquestrador (`requirements_specialist`, `sdd/orchestrator`,
`assistant/agent`) definia sua própria `backend_factory` — três closures quase
idênticas (baseline R4). Aqui elas são unificadas em `make_backend_factory`,
parametrizando apenas as rotas específicas de cada grafo.

Pertence à camada de COMPOSIÇÃO (frameworks & drivers): é o único lugar que
conhece `deepagents.backends` e o `get_config()` do LangGraph.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from deepagents.backends import (
    CompositeBackend,
    FilesystemBackend,
    StateBackend,
    StoreBackend,
)
from langgraph.config import get_config

# Namespace do Store (memória de longo prazo Postgres/pgvector).
MEMORIES_PREFIX = "/memories/"


@dataclass(frozen=True)
class FsRoute:
    """Descreve uma rota de filesystem do `CompositeBackend`.

    - `prefix`: chave da rota no `CompositeBackend` (ex.: caminho absoluto de
      saída ou `"/skills/"`).
    - `base_dir`: diretório-base do `FilesystemBackend`.
    - `per_thread`: se `True`, o `root_dir` efetivo é `base_dir / thread_id`
      (e o diretório é criado). Usado por `agent` e `assistant`.
    - `ensure_subpath`: se definido, garante (mkdir) `base_dir / ensure_subpath /
      thread_id` sem alterar o `root_dir` da rota (que permanece `base_dir`).
      Usado pelo `sdd_agent`, cujo `root_dir` é o diretório `.specify` inteiro,
      mas que precisa criar `specs/<thread_id>` por conversa.
    - `virtual_mode`: repassado ao `FilesystemBackend` (sempre `True` hoje).
    """

    prefix: str
    base_dir: Path
    per_thread: bool = False
    ensure_subpath: str | None = None
    virtual_mode: bool = True

    def resolve(self, thread_id: str) -> FilesystemBackend:
        """Constrói o `FilesystemBackend` da rota para o `thread_id` atual."""
        if self.per_thread:
            root = self.base_dir / thread_id
        else:
            root = self.base_dir

        if self.ensure_subpath is not None:
            (self.base_dir / self.ensure_subpath / thread_id).mkdir(
                parents=True, exist_ok=True
            )
        elif self.per_thread:
            root.mkdir(parents=True, exist_ok=True)

        return FilesystemBackend(root_dir=root, virtual_mode=self.virtual_mode)


def _current_thread_id() -> str:
    # thread_id via get_config(): o Runtime não expõe mais `.config` nas versões
    # novas do deepagents/langgraph (evita AttributeError no nó `model`).
    config = get_config().get("configurable", {})
    return config.get("thread_id", "default_thread")


def make_backend_factory(
    *,
    routes: list[FsRoute],
    include_store: bool = False,
) -> Callable[[Any], CompositeBackend]:
    """Cria uma `backend_factory(rt)` para `create_deep_agent(backend=...)`.

    `routes` define as rotas de filesystem específicas do grafo. `include_store`
    adiciona a rota `"/memories/"` -> `StoreBackend()` (Postgres/pgvector), usada
    pelos grafos `agent` e `sdd_agent` e omitida pelo `assistant`.
    """

    def backend_factory(rt: Any) -> CompositeBackend:
        thread_id = _current_thread_id()

        route_map: dict[str, Any] = {
            route.prefix: route.resolve(thread_id) for route in routes
        }
        # StateBackend/StoreBackend exigem o ToolRuntime (deepagents >= 0.3.x);
        # o factory recebe esse runtime e o repassa.
        if include_store:
            route_map[MEMORIES_PREFIX] = StoreBackend(rt)

        return CompositeBackend(default=StateBackend(rt), routes=route_map)

    return backend_factory
