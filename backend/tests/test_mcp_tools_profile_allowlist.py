"""Filtro de `mcp_allowlist` no `McpToolsMiddleware` (mcp-1 / REQ-005).

Overlay ativo: `load_mcp_server_config(user_id)` ∩ `mcp_allowlist`.
`None` = todos os servers do dono; `[]` = nenhuma tool MCP; lista = só
names que existem naquele `user_id`. Names desconhecidos são ignorados —
sem 500, sem lookup cross-user.
"""
from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from langchain.agents.middleware.types import ModelRequest
from langchain_core.tools import BaseTool, tool

from src.agents.unified import mcp_tools_middleware as mod
from src.agents.unified.mcp_tools_middleware import McpToolsMiddleware
from src.domain.agents import AgentProfile


@tool
def edit_file(path: str, content: str) -> str:
    """Tool nativa de edição."""
    return f"edited {path}"


def _mock_mcp_tool(name: str, *, origin: str | None = None) -> BaseTool:
    """Cria uma tool MCP mockada.

    Se `origin` for dado, estampa `metadata["mcp_server_origin"]` — a
    convenção real de `list_mcp_tools` desde a change
    `fix-mcp-multi-server-tool-attribution` (REQ-002 revisado). Sem
    `origin`, a tool não carrega origem — `_qualify_tool_names` a
    descarta (Decision 2 do design), então só serve para os testes que
    nunca a levam até lá (allowlist vazia / cross-user)."""

    @tool
    def mock_tool() -> str:
        """Mock MCP tool."""
        return f"mcp tool {name}"

    mock_tool.name = name
    mock_tool.description = f"Mock MCP tool: {name}"
    if origin is not None:
        mock_tool.metadata = {"mcp_server_origin": origin}
    return mock_tool


def _profile(*, mcp_allowlist: list[str] | None) -> AgentProfile:
    now = datetime.now(UTC)
    return AgentProfile(
        id="p1",
        user_id="user-a",
        name="Coder",
        slug="coder",
        system_prompt="x",
        mcp_allowlist=mcp_allowlist,
        created_at=now,
        updated_at=now,
    )


def _owner_connections() -> dict[str, dict]:
    return {
        "github": {"transport": "stdio", "command": "github-mcp"},
        "browser": {"transport": "stdio", "command": "browser-mcp"},
        "slack": {"transport": "stdio", "command": "slack-mcp"},
    }


async def _awrap(middleware: McpToolsMiddleware) -> tuple[set[str], McpToolsMiddleware]:
    request = ModelRequest(
        model=None,  # type: ignore[arg-type]
        tools=[edit_file],
        messages=[],
        state={},
    )

    async def handler(req: ModelRequest) -> ModelRequest:
        return req

    result = await middleware.awrap_model_call(request, handler)
    return {t.name for t in result.tools}, middleware


@pytest.mark.asyncio
async def test_none_allowlist_loads_all_owner_servers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WHEN mcp_allowlist is None THEN todos os servers do dono carregam."""
    listed: list[dict] = []
    tool_github = _mock_mcp_tool("search", origin="github")
    tool_browser = _mock_mcp_tool("nav", origin="browser")
    tool_slack = _mock_mcp_tool("post", origin="slack")

    async def fake_load(user_id: str, **_kwargs: object) -> dict:
        assert user_id == "user-a"
        return _owner_connections()

    async def fake_list(connections: dict) -> tuple[list[BaseTool], list]:
        listed.append(dict(connections))
        tools = []
        if "github" in connections:
            tools.append(tool_github)
        if "browser" in connections:
            tools.append(tool_browser)
        if "slack" in connections:
            tools.append(tool_slack)
        return tools, []

    monkeypatch.setattr(
        mod, "get_current_agent_profile", lambda: _profile(mcp_allowlist=None), raising=False
    )

    with (
        patch("src.agents.unified.mcp_tools_middleware.resolve_user_id", new=AsyncMock(return_value="user-a")),
        patch("src.agents.unified.mcp_tools_middleware.load_mcp_server_config", new=fake_load),
        patch("src.agents.unified.mcp_tools_middleware.list_mcp_tools", new=fake_list),
    ):
        names, middleware = await _awrap(McpToolsMiddleware())

    assert listed and set(listed[0]) == {"github", "browser", "slack"}
    assert "edit_file" in names
    assert "mcp__github__search" in names
    assert "mcp__browser__nav" in names
    assert "mcp__slack__post" in names
    assert set(middleware.last_load_status["servers"]) == {
        "github",
        "browser",
        "slack",
    }


@pytest.mark.asyncio
async def test_empty_allowlist_injects_no_mcp_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WHEN mcp_allowlist is [] THEN nenhuma tool MCP é injetada."""
    listed: list[dict] = []

    async def fake_load(user_id: str, **_kwargs: object) -> dict:
        return _owner_connections()

    async def fake_list(connections: dict) -> tuple[list[BaseTool], list]:
        listed.append(dict(connections))
        return [_mock_mcp_tool("github/search")], []

    monkeypatch.setattr(
        mod, "get_current_agent_profile", lambda: _profile(mcp_allowlist=[]), raising=False
    )

    with (
        patch("src.agents.unified.mcp_tools_middleware.resolve_user_id", new=AsyncMock(return_value="user-a")),
        patch("src.agents.unified.mcp_tools_middleware.load_mcp_server_config", new=fake_load),
        patch("src.agents.unified.mcp_tools_middleware.list_mcp_tools", new=fake_list),
    ):
        names, middleware = await _awrap(McpToolsMiddleware())

    assert names == {"edit_file"}
    assert listed == []
    assert middleware.last_load_status["servers"] == {}


@pytest.mark.asyncio
async def test_named_allowlist_loads_only_owner_subset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WHEN allowlist is [github, browser] e o dono tem esses servers THEN só eles carregam."""
    listed: list[dict] = []

    async def fake_load(user_id: str, **_kwargs: object) -> dict:
        return _owner_connections()

    async def fake_list(connections: dict) -> tuple[list[BaseTool], list]:
        listed.append(dict(connections))
        tools = []
        if "github" in connections:
            tools.append(_mock_mcp_tool("search", origin="github"))
        if "browser" in connections:
            tools.append(_mock_mcp_tool("nav", origin="browser"))
        if "slack" in connections:
            tools.append(_mock_mcp_tool("post", origin="slack"))
        return tools, []

    monkeypatch.setattr(
        mod,
        "get_current_agent_profile",
        lambda: _profile(mcp_allowlist=["github", "browser"]),
        raising=False,
    )

    with (
        patch("src.agents.unified.mcp_tools_middleware.resolve_user_id", new=AsyncMock(return_value="user-a")),
        patch("src.agents.unified.mcp_tools_middleware.load_mcp_server_config", new=fake_load),
        patch("src.agents.unified.mcp_tools_middleware.list_mcp_tools", new=fake_list),
    ):
        names, middleware = await _awrap(McpToolsMiddleware())

    assert listed and set(listed[0]) == {"github", "browser"}
    assert "mcp__github__search" in names
    assert "mcp__browser__nav" in names
    assert "mcp__slack__post" not in names
    assert "edit_file" in names
    assert set(middleware.last_load_status["servers"]) == {"github", "browser"}


@pytest.mark.asyncio
async def test_unknown_name_does_not_leak_another_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WHEN allowlist names a server that só existe em outro user THEN não carrega."""
    loaded_for: list[str] = []
    listed: list[dict] = []

    async def fake_load(user_id: str, **_kwargs: object) -> dict:
        loaded_for.append(user_id)
        if user_id != "user-a":
            raise AssertionError(f"cross-user MCP lookup for {user_id!r}")
        return {"slack": {"transport": "stdio", "command": "slack-mcp"}}

    async def fake_list(connections: dict) -> tuple[list[BaseTool], list]:
        listed.append(dict(connections))
        tools = []
        if "slack" in connections:
            tools.append(_mock_mcp_tool("slack/post"))
        if "github-of-b" in connections:
            tools.append(_mock_mcp_tool("github-of-b/secret"))
        return tools, []

    monkeypatch.setattr(
        mod,
        "get_current_agent_profile",
        lambda: _profile(mcp_allowlist=["github-of-b"]),
        raising=False,
    )

    with (
        patch("src.agents.unified.mcp_tools_middleware.resolve_user_id", new=AsyncMock(return_value="user-a")),
        patch("src.agents.unified.mcp_tools_middleware.load_mcp_server_config", new=fake_load),
        patch("src.agents.unified.mcp_tools_middleware.list_mcp_tools", new=fake_list),
    ):
        names, middleware = await _awrap(McpToolsMiddleware())

    assert loaded_for == ["user-a"]
    assert listed == []
    assert names == {"edit_file"}
    assert "mcp__github_of_b__secret" not in names
    assert "mcp__slack__post" not in names
    assert "github-of-b" not in middleware.last_load_status["servers"]
