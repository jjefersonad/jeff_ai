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
from deepagents.backends.protocol import EditResult, WriteResult
from langgraph.config import get_config

# Namespace do Store (memória de longo prazo Postgres/pgvector).
MEMORIES_PREFIX = "/memories/"

_WEB_USER_KEY_PREFIX = "web:"
_SKILLS_WRITE_DENIED = "Skills are read-only for this session role."


class ReadOnlyFilesystemBackend(FilesystemBackend):
    """FilesystemBackend that rejects write/edit (D14 — skills RO for user)."""

    def write(self, file_path: str, content: str) -> WriteResult:
        return WriteResult(error=_SKILLS_WRITE_DENIED)

    def edit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,  # noqa: FBT001, FBT002
    ) -> EditResult:
        return EditResult(error=_SKILLS_WRITE_DENIED)

    async def awrite(self, file_path: str, content: str) -> WriteResult:
        return self.write(file_path, content)

    async def aedit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,  # noqa: FBT001, FBT002
    ) -> EditResult:
        return self.edit(file_path, old_string, new_string, replace_all)


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
    - `read_only`: se `True`, usa `ReadOnlyFilesystemBackend` (write/edit
      recusados na borda do FS — D14).
    - `ensure_exists`: se `True`, faz `mkdir` do `root` (ex.: `files/<uid>/`).
    """

    prefix: str
    base_dir: Path
    per_thread: bool = False
    ensure_subpath: str | None = None
    virtual_mode: bool = True
    read_only: bool = False
    ensure_exists: bool = False

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
        elif self.per_thread or self.ensure_exists:
            root.mkdir(parents=True, exist_ok=True)

        cls = ReadOnlyFilesystemBackend if self.read_only else FilesystemBackend
        return cls(root_dir=root, virtual_mode=self.virtual_mode)


def _current_thread_id() -> str:
    # thread_id via get_config(): o Runtime não expõe mais `.config` nas versões
    # novas do deepagents/langgraph (evita AttributeError no nó `model`).
    config = get_config().get("configurable", {})
    return config.get("thread_id", "default_thread")


def sync_user_id_from_configurable(
    configurable: dict[str, Any] | None = None,
) -> str | None:
    """Resolve `user_id` de forma síncrona para a backend_factory.

    Prefer `configurable.user_id` se carimbado; senão `web:<uuid>` → uuid.
    Telegram/WhatsApp sem `user_id` explícito → None (fail-closed: sem files/).
    """
    if configurable is None:
        try:
            configurable = get_config().get("configurable", {}) or {}
        except Exception:  # noqa: BLE001
            return None
    explicit = configurable.get("user_id")
    if explicit:
        return str(explicit)
    user_key = configurable.get("user_key") or ""
    if isinstance(user_key, str) and user_key.startswith(_WEB_USER_KEY_PREFIX):
        return user_key.removeprefix(_WEB_USER_KEY_PREFIX) or None
    return None


def current_role() -> str:
    """`configurable.role` fail-closed para `user`."""
    try:
        role = (get_config().get("configurable", {}) or {}).get("role")
    except Exception:  # noqa: BLE001
        return "user"
    return "admin" if role == "admin" else "user"


def make_backend_factory(
    *,
    routes: list[FsRoute] | Callable[[], list[FsRoute]],
    include_store: bool = False,
) -> Callable[[Any], CompositeBackend]:
    """Cria uma `backend_factory(rt)` para `create_deep_agent(backend=...)`.

    `routes` define as rotas de filesystem do grafo — lista estática ou
    callable avaliado a cada run (role-aware). `include_store` adiciona a
    rota `"/memories/"` -> `StoreBackend()`, que dá ao agente acesso *filesystem*
    à memória de longo prazo (`ls` / `read_file` / `write_file` sobre
    `/memories/`). Hoje só o grafo `unified` usa este factory, e passa `True`.

    NOTA — não confundir com as tools de memória: `save_memory` / `search_memory`
    (`src/tools/memory_tools.py`) usam `get_store()`, o Store do LangGraph
    injetado pelo runtime via `langgraph.json`. Elas funcionam INDEPENDENTEMENTE
    de `include_store`. São dois caminhos distintos para o mesmo Postgres.
    """

    def backend_factory(rt: Any) -> CompositeBackend:
        thread_id = _current_thread_id()
        resolved_routes = routes() if callable(routes) else routes

        route_map: dict[str, Any] = {
            route.prefix: route.resolve(thread_id) for route in resolved_routes
        }
        # StateBackend/StoreBackend exigem o ToolRuntime (deepagents >= 0.3.x);
        # o factory recebe esse runtime e o repassa.
        if include_store:
            route_map[MEMORIES_PREFIX] = StoreBackend(rt)

        return CompositeBackend(default=StateBackend(rt), routes=route_map)

    return backend_factory
