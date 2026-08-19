"""Testes de `AgentProfileMiddleware` (runtime-1/2 — REQ-001, REQ-002, REQ-003, REQ-006)."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from langchain.agents.middleware.types import ModelRequest
from langchain_core.messages import SystemMessage

from src.agents.unified.agent_profile_middleware import (
    AgentProfileMiddleware,
    InvalidAgentProfileError,
    InvalidModelOverrideError,
    get_current_agent_profile,
)
from src.agents.unified.role_scoped_tools_middleware import (
    USER_DEV_TOOL_DENYLIST,
    RoleScopedToolsMiddleware,
)
from src.agents.unified.tier_config import build_interrupt_on
from src.application.use_cases.get_agent_profile import GetAgentProfile
from src.domain.agents import AgentProfile
from tests.agent_profile_repository_fakes import InMemoryAgentProfileRepository

_STATIC_PROMPT = "STATIC_UNIFIED_SYSTEM_PROMPT"


class _SpyRepo(InMemoryAgentProfileRepository):
    def __init__(self) -> None:
        super().__init__()
        self.get_default_calls = 0

    async def get_default(self, user_id: str) -> AgentProfile | None:
        self.get_default_calls += 1
        return await super().get_default(user_id)


def _profile(
    *,
    profile_id: str = "p-coder",
    user_id: str = "u1",
    name: str = "Coder",
    slug: str = "coder",
    system_prompt: str = "You are a coding assistant.",
    tools_allowlist: list[str] | None = None,
    model_override: str | None = None,
    tier: int = 1,
    archived_at: datetime | None = None,
) -> AgentProfile:
    now = datetime.now(UTC)
    return AgentProfile(
        id=profile_id,
        user_id=user_id,
        name=name,
        slug=slug,
        system_prompt=system_prompt,
        tools_allowlist=tools_allowlist,
        model_override=model_override,
        tier=tier,
        is_active=archived_at is None,
        archived_at=archived_at,
        created_at=now,
        updated_at=now,
    )


def _mw(
    repo: InMemoryAgentProfileRepository,
    *,
    resolve_model: Any | None = None,
) -> AgentProfileMiddleware:
    kwargs: dict[str, Any] = {"get_profile": GetAgentProfile(repository=repo)}
    if resolve_model is not None:
        kwargs["resolve_model"] = resolve_model
    return AgentProfileMiddleware(**kwargs)


def _request(
    *, prompt: str = _STATIC_PROMPT, tools: list[Any] | None = None
) -> ModelRequest:
    return ModelRequest(
        model=None,  # type: ignore[arg-type]
        messages=[],
        system_message=SystemMessage(content=prompt),
        tools=tools or [],
    )


def _tool_names(tools: list[Any]) -> set[str]:
    names: set[str] = set()
    for item in tools:
        if isinstance(item, dict):
            names.add(
                str(item.get("name") or item.get("function", {}).get("name") or "")
            )
        else:
            names.add(
                str(getattr(item, "name", "") or getattr(item, "__name__", "") or "")
            )
    return names


def _config(
    *,
    profile_id: str | None = None,
    user_id: str = "u1",
    tool_scope: str | None = None,
) -> dict[str, Any]:
    configurable: dict[str, Any] = {"user_key": f"web:{user_id}", "user_id": user_id}
    if profile_id is not None:
        configurable["profile_id"] = profile_id
    if tool_scope is not None:
        configurable["tool_scope"] = tool_scope
    return {"configurable": configurable}


async def test_valid_overlay_replaces_system_prompt() -> None:
    repo = _SpyRepo()
    seeded = await repo.create(_profile())
    mw = _mw(repo)
    captured: list[ModelRequest] = []

    def handler(request: ModelRequest) -> str:
        captured.append(request)
        return "ok"

    with patch(
        "src.agents.unified.agent_profile_middleware.get_config",
        return_value=_config(profile_id=seeded.id),
    ):
        await mw.abefore_agent({}, MagicMock())
        mw.wrap_model_call(_request(), handler)

    assert captured, "handler must be called"
    assert captured[0].system_prompt == seeded.system_prompt
    assert captured[0].system_prompt != _STATIC_PROMPT
    assert repo.get_default_calls == 0


async def test_sequential_profiles_replace_prompt_on_same_middleware() -> None:
    repo = _SpyRepo()
    first = await repo.create(_profile(profile_id="p-a", system_prompt="PROMPT_A"))
    second = await repo.create(
        _profile(
            profile_id="p-b",
            name="Researcher",
            slug="researcher",
            system_prompt="PROMPT_B",
        )
    )
    mw = _mw(repo)
    captured: list[str] = []

    def handler(request: ModelRequest) -> str:
        captured.append(request.system_prompt)
        return "ok"

    with patch(
        "src.agents.unified.agent_profile_middleware.get_config",
        return_value=_config(profile_id=first.id),
    ):
        await mw.abefore_agent({}, MagicMock())
        mw.wrap_model_call(_request(), handler)

    with patch(
        "src.agents.unified.agent_profile_middleware.get_config",
        return_value=_config(profile_id=second.id),
    ):
        await mw.abefore_agent({}, MagicMock())
        mw.wrap_model_call(_request(), handler)

    assert captured == ["PROMPT_A", "PROMPT_B"]
    assert repo.get_default_calls == 0


async def test_missing_profile_id_is_noop() -> None:
    repo = _SpyRepo()
    await repo.create(_profile())
    mw = _mw(repo)
    captured: list[ModelRequest] = []

    def handler(request: ModelRequest) -> str:
        captured.append(request)
        return "ok"

    with patch(
        "src.agents.unified.agent_profile_middleware.get_config",
        return_value=_config(),
    ):
        await mw.abefore_agent({}, MagicMock())
        mw.wrap_model_call(_request(tools=_NATIVE_AND_MCP), handler)
        snapshot = get_current_agent_profile()

    assert captured[0].system_prompt == _STATIC_PROMPT
    assert _tool_names(captured[0].tools) == {
        "edit_file",
        "create_docx_document",
        "git_status",
        "mcp__github__list_issues",
    }
    assert snapshot is None
    assert repo.get_default_calls == 0


async def test_archived_profile_is_refused_without_get_default() -> None:
    repo = _SpyRepo()
    seeded = await repo.create(_profile())
    await repo.archive("u1", seeded.id)
    mw = _mw(repo)

    with patch(
        "src.agents.unified.agent_profile_middleware.get_config",
        return_value=_config(profile_id=seeded.id),
    ):
        with pytest.raises(InvalidAgentProfileError, match="profile_id"):
            await mw.abefore_agent({}, MagicMock())

    assert repo.get_default_calls == 0


async def test_unknown_profile_id_is_refused_without_get_default() -> None:
    repo = _SpyRepo()
    await repo.create(_profile())
    mw = _mw(repo)

    with patch(
        "src.agents.unified.agent_profile_middleware.get_config",
        return_value=_config(profile_id="missing-id"),
    ):
        with pytest.raises(InvalidAgentProfileError, match="profile_id"):
            await mw.abefore_agent({}, MagicMock())

    assert repo.get_default_calls == 0


async def test_cross_user_profile_is_refused_without_get_default() -> None:
    repo = _SpyRepo()
    seeded = await repo.create(_profile(user_id="u1"))
    mw = _mw(repo)

    with patch(
        "src.agents.unified.agent_profile_middleware.get_config",
        return_value=_config(profile_id=seeded.id, user_id="u2"),
    ):
        with pytest.raises(InvalidAgentProfileError, match="profile_id"):
            await mw.abefore_agent({}, MagicMock())

    assert repo.get_default_calls == 0


async def test_snapshot_is_cleared_after_agent() -> None:
    repo = _SpyRepo()
    seeded = await repo.create(_profile())
    mw = _mw(repo)

    with patch(
        "src.agents.unified.agent_profile_middleware.get_config",
        return_value=_config(profile_id=seeded.id),
    ):
        await mw.abefore_agent({}, MagicMock())
        assert get_current_agent_profile() is not None
        assert get_current_agent_profile().id == seeded.id
        mw.after_agent({}, MagicMock())
        assert get_current_agent_profile() is None


class _NamedTool:
    def __init__(self, name: str) -> None:
        self.name = name


edit_file = _NamedTool("edit_file")
create_docx_document = _NamedTool("create_docx_document")
git_status = _NamedTool("git_status")
mcp_github_list_issues = _NamedTool("mcp__github__list_issues")
_NATIVE_AND_MCP = [edit_file, create_docx_document, git_status, mcp_github_list_issues]


async def _overlay_tools(
    *,
    tools_allowlist: list[str] | None,
    tier: int,
    incoming: list[Any] | None = None,
    tool_scope: str | None = None,
) -> set[str]:
    repo = _SpyRepo()
    seeded = await repo.create(
        _profile(tools_allowlist=tools_allowlist, tier=tier)
    )
    mw = _mw(repo)
    captured: list[ModelRequest] = []

    def handler(request: ModelRequest) -> str:
        captured.append(request)
        return "ok"

    with patch(
        "src.agents.unified.agent_profile_middleware.get_config",
        return_value=_config(profile_id=seeded.id, tool_scope=tool_scope),
    ):
        await mw.abefore_agent({}, MagicMock())
        mw.wrap_model_call(_request(tools=incoming or _NATIVE_AND_MCP), handler)

    return _tool_names(captured[0].tools)


async def test_empty_tools_allowlist_hides_native_tools() -> None:
    names = await _overlay_tools(tools_allowlist=[], tier=4)
    assert "edit_file" not in names
    assert "create_docx_document" not in names
    assert "git_status" not in names
    assert "mcp__github__list_issues" in names


async def test_none_tools_allowlist_does_not_cut_beyond_tier() -> None:
    names = await _overlay_tools(tools_allowlist=None, tier=2)
    assert "create_docx_document" in names
    assert "git_status" in names
    assert "edit_file" not in names
    assert "mcp__github__list_issues" in names


async def test_generated_tool_stays_visible_when_allowlist_is_none() -> None:
    """Tools fora do TIER_REGISTRY (save_generated_tool) não somem no overlay.

    `get_tier` devolve 3 para nome desconhecido — isso é o fail-safe do
    HITL, não um corte de visibilidade. Sem allowlist, o perfil vê a
    mesma tool que o agente padrão.
    """
    generated = _NamedTool("custom_weather")
    names = await _overlay_tools(
        tools_allowlist=None,
        tier=1,
        incoming=[*_NATIVE_AND_MCP, generated],
    )
    assert "custom_weather" in names
    assert "edit_file" not in names


async def test_generated_tool_is_hidden_when_not_on_allowlist() -> None:
    generated = _NamedTool("custom_weather")
    names = await _overlay_tools(
        tools_allowlist=["git_status"],
        tier=4,
        incoming=[*_NATIVE_AND_MCP, generated],
    )
    assert "custom_weather" not in names
    assert "git_status" in names


async def test_tier_1_omits_edit_file_without_touching_interrupt_on() -> None:
    names = await _overlay_tools(tools_allowlist=None, tier=1)
    assert "edit_file" not in names
    assert "git_status" in names

    interrupt = build_interrupt_on(["edit_file", "create_docx_document", "git_status"])
    assert "edit_file" in interrupt
    with patch(
        "src.agents.unified.tier_config.build_interrupt_on"
    ) as spy:
        await _overlay_tools(tools_allowlist=None, tier=1)
        spy.assert_not_called()


async def test_tier_4_still_offers_edit_file_and_interrupt_on_keeps_it() -> None:
    names = await _overlay_tools(tools_allowlist=None, tier=4)
    assert "edit_file" in names
    interrupt = build_interrupt_on(["edit_file", "create_docx_document"])
    assert "edit_file" in interrupt


async def test_full_tool_scope_still_hides_edit_file_omitted_from_allowlist() -> None:
    """WHEN tool_scope is FULL and tools_allowlist omits edit_file THEN it is unavailable."""
    names = await _overlay_tools(
        tools_allowlist=["git_status", "create_docx_document"],
        tier=4,
        tool_scope="full",
    )
    assert "edit_file" not in names
    assert "git_status" in names


async def test_restricted_tool_scope_hides_edit_file_even_if_allowlisted() -> None:
    """Most restrictive wins: RESTRICTED ∩ allowlist that includes edit_file."""
    names = await _overlay_tools(
        tools_allowlist=["git_status", "edit_file", "create_docx_document"],
        tier=4,
        tool_scope="restricted",
    )
    assert "edit_file" not in names
    assert "git_status" in names


async def test_allowlist_cannot_grant_role_denied_tool() -> None:
    repo = _SpyRepo()
    seeded = await repo.create(
        _profile(
            tools_allowlist=["git_status", "create_docx_document"],
            tier=4,
        )
    )
    profile_mw = _mw(repo)
    role_mw = RoleScopedToolsMiddleware(role="user")
    captured: list[ModelRequest] = []

    def handler(request: ModelRequest) -> str:
        captured.append(request)
        return "ok"

    def after_profile(request: ModelRequest) -> str:
        return role_mw.wrap_model_call(request, handler)

    with patch(
        "src.agents.unified.agent_profile_middleware.get_config",
        return_value=_config(profile_id=seeded.id),
    ):
        await profile_mw.abefore_agent({}, MagicMock())
        profile_mw.wrap_model_call(_request(tools=_NATIVE_AND_MCP), after_profile)

    names = _tool_names(captured[0].tools)
    assert "git_status" in USER_DEV_TOOL_DENYLIST
    assert "git_status" not in names
    assert "create_docx_document" in names


class _SentinelModel:
    def __init__(self, label: str) -> None:
        self.label = label


_GRAPH_MODEL = _SentinelModel("unified")
_OVERRIDE_MODEL = _SentinelModel("override")


def _resolve_ok(name: str) -> _SentinelModel:
    if name == "ok-model":
        return _OVERRIDE_MODEL
    raise InvalidModelOverrideError(f"model_override inválido: {name!r}")


async def test_model_override_swaps_the_request_model() -> None:
    repo = _SpyRepo()
    seeded = await repo.create(_profile(model_override="ok-model", tier=4))
    mw = _mw(repo, resolve_model=_resolve_ok)
    captured: list[ModelRequest] = []

    def handler(request: ModelRequest) -> str:
        captured.append(request)
        return "ok"

    with patch(
        "src.agents.unified.agent_profile_middleware.get_config",
        return_value=_config(profile_id=seeded.id),
    ):
        await mw.abefore_agent({}, MagicMock())
        request = _request()
        request = request.override(model=_GRAPH_MODEL)  # type: ignore[arg-type]
        mw.wrap_model_call(request, handler)

    assert captured[0].model is _OVERRIDE_MODEL
    assert captured[0].model is not _GRAPH_MODEL


async def test_invalid_model_override_fails_closed() -> None:
    repo = _SpyRepo()
    seeded = await repo.create(_profile(model_override="not-a-real-model", tier=4))
    mw = _mw(repo, resolve_model=_resolve_ok)
    captured: list[ModelRequest] = []

    def handler(request: ModelRequest) -> str:
        captured.append(request)
        return "ok"

    with patch(
        "src.agents.unified.agent_profile_middleware.get_config",
        return_value=_config(profile_id=seeded.id),
    ):
        await mw.abefore_agent({}, MagicMock())
        request = _request()
        request = request.override(model=_GRAPH_MODEL)  # type: ignore[arg-type]
        with pytest.raises(InvalidModelOverrideError, match="model_override"):
            mw.wrap_model_call(request, handler)

    assert captured == []
