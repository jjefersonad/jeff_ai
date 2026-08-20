"""`AgentProfileMiddleware` — overlay de perfil no grafo `unified` compilado.

Resolve `configurable.profile_id` uma vez por run (`before_agent` /
`abefore_agent`), publica o `AgentProfile` num **cache em `self`** (chave
`(user_id, profile_id)`, TTL `_SNAPSHOT_TTL_SECONDS`), substitui o system
prompt, filtra tools nativas (`tools_allowlist` ∩ teto de `tier` ∩
`tool_scope` da tarefa, o mais restritivo) e aplica `model_override` em
`wrap_model_call` (catálogo de `unified_model`, fail-closed).

## Por que cache em `self` (e não `ContextVar`)

O langchain `factory.py:1511-1529` registra cada hook (`before_agent`,
`wrap_model_call`, `after_agent`) como **nó separado do grafo**, e o
LangGraph executa cada nó em uma `asyncio.Task` isolada. `ContextVar`
**não atravessa tasks** — um valor setado em uma task não é visível em
outra. Como `before_agent` e `wrap_model_call` rodam em tasks separadas
na prática (cada `graph.add_node` vira um `RunnableCallable` agendado), o
`ContextVar` zerava entre eles e o modelo recebia o `_SYSTEM_PROMPT`
estático do `unified` em vez de `profile.system_prompt`.

A correção é armazenar o snapshot em `self._profile_snapshot` — uma vez
que o middleware é instanciado pelo `build_unified()`, ele vive durante
toda a vida do processo, então o cache persiste entre tasks. TTL de
60 segundos cobre uma run inteira (HITL pause + resume) sem custo
adicional de I/O.

Sem `profile_id` é no-op no prompt; `tool_scope=restricted` ainda omite
nativas de tier 3+. Miss, cross-user, arquivado ou `user_id` irresolvível
recusam o run — nunca chamam `get_default`. Não recompila `interrupt_on`
e não anexa usage callback (o de `build_unified().with_config` permanece).
Registrado em `build_unified()` depois de `EnvelopeLifecycleMiddleware`.
"""
from __future__ import annotations

import asyncio
import os
import time
from collections.abc import Callable, Sequence
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ModelRequest
from langchain_core.messages import SystemMessage

from src.agents.unified.tier_config import TIER_REGISTRY, get_tier
from src.application.use_cases.get_agent_profile import GetAgentProfile
from src.composition.backends import sync_user_id_from_configurable
from src.domain.agents import (
    AgentProfile,
    InvalidAgentProfileError,
    InvalidModelOverrideError,
)
from src.infrastructure.ownership.store import resolve_user_id

try:
    from langgraph.config import get_config
except ImportError:  # pragma: no cover

    def get_config() -> dict[str, Any]:  # type: ignore[misc]
        return {}


_INVALID_PROFILE_ID = "profile_id inválido"
_MCP_TOOL_PREFIX = "mcp__"
_RESTRICTED_MAX_TIER = 2
# Snapshot TTL: cobre uma run inteira (HITL pause + resume raramente
# passa de 1 min). Após esse tempo, o cache miss é tratado como
# no-op pelo `_overlay_request` (mesmo comportamento de `profile_id`
# ausente) — não há crash, não há exception.
_SNAPSHOT_TTL_SECONDS = 60


def get_current_agent_profile() -> AgentProfile | None:
    """Compat: helper legado. Retorna `None` se chamado sem middleware ativo.
    Use `AgentProfileMiddleware._lookup_snapshot(user_id, profile_id)` para
    ler o cache de uma instância específica. Mantido apenas para não
    quebrar imports de testes legados.
    """
    return None


def _tool_name(tool: Any) -> str:
    if isinstance(tool, dict):
        return str(tool.get("name") or tool.get("function", {}).get("name") or "")
    return str(getattr(tool, "name", "") or getattr(tool, "__name__", "") or "")


def _configurable() -> dict[str, Any]:
    try:
        return get_config().get("configurable", {}) or {}
    except Exception:  # noqa: BLE001 — fora de runnable context
        return {}


def _default_resolve_model(name: str) -> Any:
    """Lazy: evita importar ChatOllama nos testes que não usam override."""
    from src.models.resolve_unified_model import resolve_unified_model

    return resolve_unified_model(name)


class AgentProfileMiddleware(AgentMiddleware[Any, Any, Any]):
    """Publica o snapshot de `AgentProfile`, troca prompt/tools e o modelo."""

    def __init__(
        self,
        *,
        get_profile: GetAgentProfile | None = None,
        resolve_model: Callable[[str], Any] | None = None,
    ) -> None:
        """Recebe o caso de uso do perfil e o resolvedor de `model_override`.

        `get_profile` omitido constrói `GetAgentProfile` + repositório
        Postgres na primeira resolução (fábrica `build_unified()` sem
        Postgres no import).
        """
        super().__init__()
        self._get_profile = get_profile
        self._resolve_model = resolve_model or _default_resolve_model
        # Snapshot cache: chave `(user_id, profile_id)`, valor
        # `(AgentProfile, resolved_at_monotonic)`. O middleware é
        # instanciado uma vez no boot (`build_unified()`), então o
        # dicionário vive durante toda a vida do processo e atravessa
        # as fronteiras de `asyncio.Task` que o LangGraph cria entre
        # os hooks do middleware.
        self._profile_snapshot: dict[
            tuple[str, str], tuple[AgentProfile, float]
        ] = {}

    def _profile_use_case(self) -> GetAgentProfile:
        if self._get_profile is None:
            from src.infrastructure.persistence.agent_profile_repository import (
                PostgresAgentProfileRepository,
            )

            self._get_profile = GetAgentProfile(
                repository=PostgresAgentProfileRepository(
                    os.environ.get("POSTGRES_URI", "")
                )
            )
        return self._get_profile

    def _lookup_snapshot(
        self, user_id: str, profile_id: str
    ) -> AgentProfile | None:
        """Lê o cache, considerando TTL. `None` se miss, stale ou ausente."""
        entry = self._profile_snapshot.get((user_id, profile_id))
        if entry is None:
            return None
        profile, resolved_at = entry
        if (time.monotonic() - resolved_at) > _SNAPSHOT_TTL_SECONDS:
            # Cache stale: evict sob demanda. Próximo `before_agent`
            # repopula via `_apublish_snapshot`.
            self._profile_snapshot.pop((user_id, profile_id), None)
            return None
        return profile

    async def _apublish_snapshot(self) -> None:
        configurable = _configurable()
        raw_profile_id = configurable.get("profile_id")
        if raw_profile_id is None:
            return
        profile_id = str(raw_profile_id).strip()
        if not profile_id:
            return

        user_id = sync_user_id_from_configurable(configurable)
        if not user_id:
            user_id = await resolve_user_id()
        if not user_id:
            raise InvalidAgentProfileError(_INVALID_PROFILE_ID)

        profile = await self._profile_use_case().execute(
            user_id=user_id,
            profile_id=profile_id,
        )
        if profile is None or profile.archived_at is not None:
            raise InvalidAgentProfileError(_INVALID_PROFILE_ID)
        self._profile_snapshot[(user_id, profile_id)] = (profile, time.monotonic())

    def before_agent(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        """Resolve o snapshot de perfil via `asyncio.run` no caminho síncrono."""
        asyncio.run(self._apublish_snapshot())
        return None

    async def abefore_agent(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        """Resolve o snapshot de perfil no caminho assíncrono."""
        await self._apublish_snapshot()
        return None

    # `after_agent` / `aafter_agent` foram removidos (`fix-agent-profile-
    # middleware-contextvar-leak`): o snapshot vive no cache por
    # `(user_id, profile_id)`, não por turn, então limpar no fim da run
    # só adicionaria overhead sem valor. O TTL de 60s + cleanup on-read
    # garante que entradas stale não persistam.

    def _filter_native_tools(
        self,
        tools: Sequence[Any],
        profile: AgentProfile,
    ) -> list[Any]:
        """Intersecta tools nativas com `tools_allowlist` e o teto de `tier`.

        Tools `mcp__*` ficam intocadas aqui — o filtro de servidores
        (`mcp_allowlist`) é aplicado em `McpToolsMiddleware` no load.
        `None` na allowlist não corta além do teto de catálogo; `[]` omite
        todas as nativas. Tools fora de `TIER_REGISTRY` (geradas via
        `save_generated_tool`) não somem só porque `get_tier` devolve 3:
        o teto vale para o catálogo; o HITL continua no `interrupt_on`
        deny-by-default. Não adiciona tools que não estavam no request.
        """
        allowlist = profile.tools_allowlist
        kept: list[Any] = []
        for tool in tools:
            name = _tool_name(tool)
            if name.startswith(_MCP_TOOL_PREFIX):
                kept.append(tool)
                continue
            if allowlist is not None and name not in allowlist:
                continue
            catalog_tier = TIER_REGISTRY.get(name)
            if catalog_tier is not None and catalog_tier > profile.tier:
                continue
            kept.append(tool)
        return kept

    def _apply_tool_scope(self, tools: Sequence[Any]) -> list[Any]:
        """RESTRICTED omite nativas acima do tier 2; omitido/FULL não corta.

        Tools `mcp__*` ficam intocadas aqui (`McpToolsMiddleware` +
        `mcp_allowlist`). Chat web não carimba `tool_scope` — não restringe.
        """
        scope = str(_configurable().get("tool_scope") or "").strip().lower()
        if scope != "restricted":
            return list(tools)
        kept: list[Any] = []
        for tool in tools:
            name = _tool_name(tool)
            if name.startswith(_MCP_TOOL_PREFIX):
                kept.append(tool)
                continue
            if get_tier(name) > _RESTRICTED_MAX_TIER:
                continue
            kept.append(tool)
        return kept

    def _resolve_profile_from_configurable(self) -> AgentProfile | None:
        """Lê o profile do cache usando `user_id` e `profile_id` do configurable.

        Retorna `None` se faltar chave ou se o cache miss. O caller
        (`_overlay_request`) trata `None` como "sem overlay".
        """
        configurable = _configurable()
        user_id = sync_user_id_from_configurable(configurable)
        if not user_id:
            return None
        raw_profile_id = configurable.get("profile_id")
        if raw_profile_id is None:
            return None
        profile_id = str(raw_profile_id).strip()
        if not profile_id:
            return None
        return self._lookup_snapshot(user_id, profile_id)

    def _overlay_request(self, request: ModelRequest) -> ModelRequest:
        profile = self._resolve_profile_from_configurable()
        tools = list(request.tools)
        if profile is not None:
            tools = self._filter_native_tools(tools, profile)
        tools = self._apply_tool_scope(tools)
        if profile is None:
            if tools == list(request.tools):
                return request
            return request.override(tools=tools)
        overrides: dict[str, Any] = {
            "system_message": SystemMessage(content=profile.system_prompt),
            "tools": tools,
        }
        if profile.model_override:
            overrides["model"] = self._resolve_model(profile.model_override)
        return request.override(**overrides)

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Any],
    ) -> Any:
        """Aplica prompt, filtro de tools nativas e `model_override` do snapshot."""
        return handler(self._overlay_request(request))

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Any],
    ) -> Any:
        """Aplica prompt, filtro de tools nativas e `model_override` no caminho assíncrono."""
        return await handler(self._overlay_request(request))


__all__ = [
    "AgentProfileMiddleware",
    "InvalidAgentProfileError",
    "InvalidModelOverrideError",
    "get_current_agent_profile",
]
