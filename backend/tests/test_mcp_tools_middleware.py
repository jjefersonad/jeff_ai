"""Tests for `McpToolsMiddleware` (task `unified-agent-realignment-task-mcp-2`,
revisado pela task `user-scoped-mcp-config-storage-task-middleware-1`).

Covers the core acceptance criteria using async-only approach to avoid event
loop issues, plus one sync-path regression test. Since `McpToolsMiddleware`
now resolves the running session's `user_id` via `resolve_user_id()` instead
of reading a `config_path`, every test here mocks `resolve_user_id` (and
`load_mcp_server_config`/`list_mcp_tools`, as before) rather than writing a
JSON file to disk.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain.agents.middleware.types import ModelRequest
from langchain_core.tools import BaseTool, tool

from src.agents.unified.effects import CAPABILITY_NAMES, Capability
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


def _patch_resolve_user_id(user_id: str | None):
    return patch(
        "src.agents.unified.mcp_tools_middleware.resolve_user_id",
        new=AsyncMock(return_value=user_id),
    )


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
async def test_mcp_tools_scoped_to_resolved_user() -> None:
    """unit-1 (REQ-009): tools carregadas vêm só do `user_id` que
    `resolve_user_id()` resolveu para a sessão corrente — um servidor de
    outro usuário nunca entra em `list_mcp_tools`."""
    connections_by_user = {
        "user-a": {"srv-a": {"transport": "stdio", "command": "cmd-a"}},
        "user-b": {"srv-b": {"transport": "stdio", "command": "cmd-b"}},
    }
    tool_a = _mock_mcp_tool("srv-a/tool_a")

    async def fake_load_mcp_server_config(user_id: str, **_kwargs: object) -> dict:
        return connections_by_user[user_id]

    async def fake_list_mcp_tools(connections: dict) -> tuple[list[BaseTool], list]:
        assert set(connections) == {"srv-a"}  # nunca vê o servidor de user-b
        return [tool_a], []

    with (
        _patch_resolve_user_id("user-a"),
        patch(
            "src.agents.unified.mcp_tools_middleware.load_mcp_server_config",
            new=fake_load_mcp_server_config,
        ),
        patch(
            "src.agents.unified.mcp_tools_middleware.list_mcp_tools",
            new=fake_list_mcp_tools,
        ),
    ):
        middleware = McpToolsMiddleware()
        request = ModelRequest(
            model=None,  # type: ignore[arg-type]
            tools=[edit_file],
            messages=[],
            state={},
        )

        async def handler(req: ModelRequest) -> ModelRequest:
            return req

        result = await middleware.awrap_model_call(request, handler)

        assert len(result.tools) == 2  # 1 nativa + 1 MCP de user-a
        tool_names = {t.name for t in result.tools}
        assert tool_names == {"edit_file", "mcp__srv_a__tool_a"}


def test_wrap_model_call_sync_path_scopes_to_resolved_user() -> None:
    """Mesmo comportamento do teste acima, mas pela via síncrona
    (`wrap_model_call`/`_load_mcp_tools`), que faz a ponte pro loop async
    via `asyncio.run`."""
    tool_a = _mock_mcp_tool("srv-a/tool_a")

    with (
        _patch_resolve_user_id("user-a"),
        patch(
            "src.agents.unified.mcp_tools_middleware.load_mcp_server_config",
            new=AsyncMock(return_value={"srv-a": {"transport": "stdio", "command": "cmd-a"}}),
        ),
        patch(
            "src.agents.unified.mcp_tools_middleware.list_mcp_tools",
            new=AsyncMock(return_value=([tool_a], [])),
        ),
    ):
        middleware = McpToolsMiddleware()
        request = ModelRequest(
            model=None,  # type: ignore[arg-type]
            tools=[edit_file],
            messages=[],
            state={},
        )

        def handler(req: ModelRequest) -> ModelRequest:
            return req

        result = middleware.wrap_model_call(request, handler)

        tool_names = {t.name for t in result.tools}
        assert tool_names == {"edit_file", "mcp__srv_a__tool_a"}


@pytest.mark.asyncio
async def test_unresolvable_user_loads_no_mcp_tools() -> None:
    """unit-2 (REQ-009): `resolve_user_id()` devolvendo `None` (sessão sem
    vínculo — ex.: canal Telegram/WhatsApp não linkado) não trava o agente:
    zero tools MCP, tools nativas intactas, nenhuma exceção propaga."""
    with _patch_resolve_user_id(None):
        middleware = McpToolsMiddleware()
        request = ModelRequest(
            model=None,  # type: ignore[arg-type]
            tools=[edit_file],
            messages=[],
            state={},
        )

        async def handler(req: ModelRequest) -> ModelRequest:
            return req

        result = await middleware.awrap_model_call(request, handler)

        assert len(result.tools) == 1
        assert result.tools[0].name == "edit_file"
        assert middleware.connection_errors == []


@pytest.mark.asyncio
async def test_server_offline_graceful_degradation():
    """REQ-004: Servidor offline não trava o agente."""
    error = McpServerConnectionError("offline", "connection refused")
    with (
        _patch_resolve_user_id("user-a"),
        patch(
            "src.agents.unified.mcp_tools_middleware.load_mcp_server_config",
            new=AsyncMock(return_value={"offline": {"transport": "stdio", "command": "npx"}}),
        ),
        patch(
            "src.agents.unified.mcp_tools_middleware.list_mcp_tools",
            new=AsyncMock(return_value=([], [error])),
        ),
    ):
        middleware = McpToolsMiddleware()
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
async def test_mcp_tools_subject_to_envelope(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """REQ-003 + REQ-008 (revisto por `remove-mcp-unknown-failsafe`): uma tool
    MCP sem override classifica como `NETWORK` (piso) e passa sem concessão
    explícita; uma tool MCP com override manual mais restrito continua
    exigindo concessão do envelope como qualquer outra capability fora do
    piso."""
    # Tool MCP desconhecida, sem override → NETWORK (piso)
    hostile_tool = _mock_mcp_tool("hostile/delete_everything")

    request = ModelRequest(
        model=None,  # type: ignore[arg-type]
        tools=[],
        messages=[],
        state={},
    )

    async def handler(req: ModelRequest) -> ModelRequest:
        return req

    with (
        _patch_resolve_user_id("user-a"),
        patch(
            "src.agents.unified.mcp_tools_middleware.load_mcp_server_config",
            new=AsyncMock(return_value={"hostile": {"transport": "stdio", "command": "python"}}),
        ),
        patch(
            "src.agents.unified.mcp_tools_middleware.list_mcp_tools",
            new=AsyncMock(return_value=([hostile_tool], [])),
        ),
    ):
        mcp_middleware = McpToolsMiddleware()
        # Envelope sem nenhuma concessão além do piso
        envelope_middleware = EnvelopeMiddleware(granted={Capability.READ})

        # MCP adiciona a tool
        after_mcp = await mcp_middleware.awrap_model_call(request, handler)
        assert len(after_mcp.tools) == 1

        # NETWORK está no piso — passa sem concessão explícita
        after_envelope = await envelope_middleware.awrap_model_call(after_mcp, handler)
        assert len(after_envelope.tools) == 1
        assert after_envelope.tools[0].name == "mcp__hostile__delete_everything"

    # Override manual mais restrito (fora do piso) ainda gateia normalmente.
    import functools

    import src.agents.unified.mcp_tool_overrides as overrides_module

    override_path = tmp_path / "mcp_tool_overrides.json"
    monkeypatch.setattr(
        overrides_module,
        "get_override",
        functools.partial(overrides_module.get_override, path=override_path),
    )
    overrides_module.set_override(
        "mcp__hostile__delete_everything",
        "write_existing",
        valid_capabilities=CAPABILITY_NAMES,
        path=override_path,
    )

    with (
        _patch_resolve_user_id("user-a"),
        patch(
            "src.agents.unified.mcp_tools_middleware.load_mcp_server_config",
            new=AsyncMock(return_value={"hostile": {"transport": "stdio", "command": "python"}}),
        ),
        patch(
            "src.agents.unified.mcp_tools_middleware.list_mcp_tools",
            new=AsyncMock(return_value=([hostile_tool], [])),
        ),
    ):
        after_mcp2 = await mcp_middleware.awrap_model_call(request, handler)

        # write_existing não está no piso nem em granted={READ} — bloqueada
        after_envelope2 = await envelope_middleware.awrap_model_call(after_mcp2, handler)
        assert len(after_envelope2.tools) == 0

        # Concedendo write_existing explicitamente, passa
        envelope_with_write = EnvelopeMiddleware(
            granted={Capability.READ, Capability.WRITE_EXISTING}
        )
        after_envelope3 = await envelope_with_write.awrap_model_call(after_mcp2, handler)
        assert len(after_envelope3.tools) == 1
        assert after_envelope3.tools[0].name == "mcp__hostile__delete_everything"


# --------------------------------------------------------------------------- #
# Tests for `last_load_status` (foundation-1 of fix-mcp-tool-not-exposed-error)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_last_load_status_empty_when_user_unresolvable(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """unit-1 (REQ-002): `resolve_user_id() -> None` (sessão sem vínculo)
    MUST populate `last_load_status` with `loaded_at`, `servers={}`,
    `tools_by_name={}` — sem exceção, sem log de erro. Prova a segurança da
    infra para sessões web/Telegram/WhatsApp ainda não linkadas."""
    import datetime as _dt

    with _patch_resolve_user_id(None):
        middleware = McpToolsMiddleware()
        request = ModelRequest(
            model=None,  # type: ignore[arg-type]
            tools=[edit_file],
            messages=[],
            state={},
        )

        async def handler(req: ModelRequest) -> ModelRequest:
            return req

        with caplog.at_level("INFO"):
            await middleware.awrap_model_call(request, handler)

    assert hasattr(middleware, "last_load_status")
    assert middleware.last_load_status["servers"] == {}
    assert middleware.last_load_status["tools_by_name"] == {}
    # loaded_at é uma string ISO 8601 parseável
    parsed = _dt.datetime.fromisoformat(middleware.last_load_status["loaded_at"])
    assert parsed.tzinfo is not None
    assert middleware.connection_errors == []


@pytest.mark.asyncio
async def test_last_load_status_records_successful_server() -> None:
    """unit-2 (REQ-002): servidor que conecta com sucesso MUST aparecer em
    `last_load_status.servers[name]` com `{configured=True, connected=True,
    tool_count=N, last_error=None}` e cada tool qualificada em
    `tools_by_name[mcp__<server>__<tool>] = server_name`."""
    zernio_tool_a = _mock_mcp_tool("zernio/posts_create")
    zernio_tool_b = _mock_mcp_tool("zernio/posts_list")

    with (
        _patch_resolve_user_id("user-x"),
        patch(
            "src.agents.unified.mcp_tools_middleware.load_mcp_server_config",
            new=AsyncMock(
                return_value={"zernio": {"transport": "stdio", "command": "zernio"}}
            ),
        ),
        patch(
            "src.agents.unified.mcp_tools_middleware.list_mcp_tools",
            new=AsyncMock(return_value=([zernio_tool_a, zernio_tool_b], [])),
        ),
    ):
        middleware = McpToolsMiddleware()
        request = ModelRequest(
            model=None,  # type: ignore[arg-type]
            tools=[edit_file],
            messages=[],
            state={},
        )

        async def handler(req: ModelRequest) -> ModelRequest:
            return req

        await middleware.awrap_model_call(request, handler)

    assert middleware.last_load_status["servers"]["zernio"] == {
        "configured": True,
        "connected": True,
        "tool_count": 2,
        "last_error": None,
    }
    assert middleware.last_load_status["tools_by_name"] == {
        "mcp__zernio__posts_create": "zernio",
        "mcp__zernio__posts_list": "zernio",
    }
    # connection_errors preserva o contrato original
    assert middleware.connection_errors == []


@pytest.mark.asyncio
async def test_last_load_status_records_failed_server_no_creds() -> None:
    """unit-3 (REQ-002 + REQ-007 sem leak): servidor que falha ao conectar
    MUST aparecer em `last_load_status.servers[name]` com `connected=False,
    tool_count=0, last_error='<type>: <msg>'` — e esse `last_error` MUST
    NÃO conter nenhum valor de `env`/`headers` da config (defesa contra
    leak de credenciais em mensagens de erro upstream)."""
    import src.agents.unified.mcp_client as client_module

    SECRET_TOKEN = "ABCDEF-my-secret-bearer-token-do-not-leak"
    SECRET_HEADER = "X-Internal-Authorization"

    async def fake_list(connections: dict) -> tuple[list, list]:
        # Simula um servidor MCP cujo cliente inclui o header de auth
        # na exception message (cenário adversarial, REQ-007 do mcp-client).
        only = next(iter(connections))
        err = client_module.McpServerConnectionError(
            only,
            f"upstream refused with debug: {SECRET_HEADER}: {SECRET_TOKEN}",
        )
        return [], [err]   

    with (
        _patch_resolve_user_id("user-x"),
        patch(
            "src.agents.unified.mcp_tools_middleware.load_mcp_server_config",
            new=AsyncMock(
                return_value={
                    "zernio": {
                        "transport": "http",
                        "url": "https://zernio.example.com",
                        "headers": {
                            SECRET_HEADER: f"Bearer {SECRET_TOKEN}",
                        },
                    }
                }
            ),
        ),
        patch(
            "src.agents.unified.mcp_tools_middleware.list_mcp_tools",
            new=fake_list,
        ),
    ):
        middleware = McpToolsMiddleware()
        request = ModelRequest(
            model=None,  # type: ignore[arg-type]
            tools=[edit_file],
            messages=[],
            state={},
        )

        async def handler(req: ModelRequest) -> ModelRequest:
            return req

        await middleware.awrap_model_call(request, handler)

    record = middleware.last_load_status["servers"]["zernio"]
    assert record["configured"] is True
    assert record["connected"] is False
    assert record["tool_count"] == 0
    assert isinstance(record["last_error"], str) and record["last_error"]
    # REQ-007: o last_error NÃO pode vazar o header nem o token
    assert SECRET_TOKEN not in record["last_error"]
    assert SECRET_HEADER not in record["last_error"]
    # connection_errors preserva o contrato (sem mutar)
    assert len(middleware.connection_errors) == 1
    assert middleware.connection_errors[0].server_name == "zernio"
