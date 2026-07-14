"""Simplified tests for `McpToolsMiddleware` (task `unified-agent-realignment-task-mcp-2`).

Covers the core acceptance criteria using async-only approach to avoid event loop issues.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain.agents.middleware.types import ModelRequest
from langchain_core.tools import BaseTool, tool

from src.agents.unified.effects import Capability
from src.agents.unified.envelope_middleware import EnvelopeMiddleware
from src.agents.unified.mcp_client import McpServerConnectionError
from src.agents.unified.mcp_tools_middleware import (
    McpToolsMiddleware,
    _qualify_tool_names,
)


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
@tool
def edit_file(path: str, content: str) -> str:
    """Tool nativa de edição."""
    return f"edited {path}"


@tool
def read_file(path: str) -> str:
    """Tool nativa de leitura."""
    return f"read {path}"


def _mock_mcp_tool(name: str) -> BaseTool:
    """Cria uma tool MCP mockada."""

    @tool
    def mock_tool() -> str:
        """Mock MCP tool function."""
        return f"mcp tool {name}"

    mock_tool.name = name
    mock_tool.description = f"Mock MCP tool: {name}"
    return mock_tool


# --------------------------------------------------------------------------- #
# Core tests
# --------------------------------------------------------------------------- #
def test_qualify_tool_names():
    """REQ-002: Qualifica tools MCP por servidor."""
    tools = [
        _mock_mcp_tool("servidor1/read_db"),
        _mock_mcp_tool("my-server/edit_file"),
    ]
    connections = {"servidor1": MagicMock(), "my-server": MagicMock()}

    qualified = _qualify_tool_names(tools, connections)

    assert qualified[0].name == "mcp__servidor1__read_db"
    assert qualified[1].name == "mcp__my_server__edit_file"  # hífen → underscore


@pytest.mark.asyncio
async def test_mcp_tools_injected_async():
    """REQ-002: Tools MCP adicionadas ao request."""
    config = {"mcpServers": {"test": {"command": "node", "args": ["server.js"]}}}
    config_path = "/tmp/test_mcp.json"
    Path(config_path).write_text(json.dumps(config))

    mock_tools = [_mock_mcp_tool("test/read_db")]
    with patch(
        "src.agents.unified.mcp_tools_middleware.list_mcp_tools",
        new=AsyncMock(return_value=(mock_tools, [])),
    ):
        middleware = McpToolsMiddleware(config_path=config_path)
        request = ModelRequest(
            model=None,  # type: ignore[arg-type]
            tools=[edit_file],
            messages=[],
            state={},
        )

        async def handler(req: ModelRequest) -> ModelRequest:
            return req

        result = await middleware.awrap_model_call(request, handler)

        assert len(result.tools) == 2  # 1 nativa + 1 MCP
        tool_names = {t.name for t in result.tools}
        assert "edit_file" in tool_names
        assert "mcp__test__read_db" in tool_names


@pytest.mark.asyncio
async def test_server_offline_graceful_degradation():
    """REQ-004: Servidor offline não trava o agente."""
    config = {"mcpServers": {"offline": {"command": "npx", "args": ["nonexistent"]}}}
    config_path = "/tmp/test_mcp_offline.json"
    Path(config_path).write_text(json.dumps(config))

    error = McpServerConnectionError("offline", "connection refused")
    with patch(
        "src.agents.unified.mcp_tools_middleware.list_mcp_tools",
        new=AsyncMock(return_value=([], [error])),
    ):
        middleware = McpToolsMiddleware(config_path=config_path)
        request = ModelRequest(
            model=None,  # type: ignore[arg-type]
            tools=[edit_file],
            messages=[],
            state={},
        )

        async def handler(req: ModelRequest) -> ModelRequest:
            return req

        result = await middleware.awrap_model_call(request, handler)

        # Só a tool nativa sobra
        assert len(result.tools) == 1
        assert result.tools[0].name == "edit_file"
        # Erro registrado
        assert len(middleware.connection_errors) == 1
        assert middleware.connection_errors[0].server_name == "offline"


@pytest.mark.asyncio
async def test_mcp_tools_subject_to_envelope():
    """REQ-003 + REQ-008: Tools MCP filtradas pelo envelope."""
    config = {"mcpServers": {"hostile": {"command": "python", "args": ["hostile.py"]}}}
    config_path = "/tmp/test_mcp_hostile.json"
    Path(config_path).write_text(json.dumps(config))

    # Tool MCP desconhecida → UNKNOWN
    hostile_tool = _mock_mcp_tool("hostile/delete_everything")

    with patch(
        "src.agents.unified.mcp_tools_middleware.list_mcp_tools",
        new=AsyncMock(return_value=([hostile_tool], [])),
    ):
        mcp_middleware = McpToolsMiddleware(config_path=config_path)
        # Envelope SEM `UNKNOWN` concedido
        envelope_middleware = EnvelopeMiddleware(granted={Capability.READ})

        request = ModelRequest(
            model=None,  # type: ignore[arg-type]
            tools=[],
            messages=[],
            state={},
        )

        async def handler(req: ModelRequest) -> ModelRequest:
            return req

        # MCP adiciona a tool
        after_mcp = await mcp_middleware.awrap_model_call(request, handler)
        assert len(after_mcp.tools) == 1

        # Envelope remove (UNKNOWN negado)
        after_envelope = await envelope_middleware.awrap_model_call(after_mcp, handler)
        assert len(after_envelope.tools) == 0  # tool bloqueada

    # Agora concede UNKNOWN
    with patch(
        "src.agents.unified.mcp_tools_middleware.list_mcp_tools",
        new=AsyncMock(return_value=([hostile_tool], [])),
    ):
        envelope_with_unknown = EnvelopeMiddleware(
            granted={Capability.READ, Capability.UNKNOWN}
        )

        after_mcp2 = await mcp_middleware.awrap_model_call(request, handler)
        after_envelope2 = await envelope_with_unknown.awrap_model_call(
            after_mcp2, handler
        )

        # Agora passa
        assert len(after_envelope2.tools) == 1
        assert after_envelope2.tools[0].name == "mcp__hostile__delete_everything"


@pytest.mark.asyncio
async def test_missing_config_file():
    """REQ-001: Config ausente não trava."""
    middleware = McpToolsMiddleware(config_path="/nonexistent/path.json")
    request = ModelRequest(
        model=None,  # type: ignore[arg-type]
        tools=[edit_file],
        messages=[],
        state={},
    )

    async def handler(req: ModelRequest) -> ModelRequest:
        return req

    result = await middleware.awrap_model_call(request, handler)

    # Só a nativa
    assert len(result.tools) == 1
    assert result.tools[0].name == "edit_file"
