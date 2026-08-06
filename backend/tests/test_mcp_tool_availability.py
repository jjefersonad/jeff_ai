"""Tests for `McpToolAvailabilityMiddleware` (foundation-2 / skeleton-1 / etc.
of the change `fix-mcp-tool-not-exposed-error`).

Covers a sub-agent of the `unified` graph that intercepts `wrap_tool_call`
for tool calls with prefix `mcp__*` whose target tool is NOT in the model-
bound set delivered by `McpToolsMiddleware`. Categorizes the failure into
`not_configured` / `not_connected` / `unknown_tool_name` / `filtered_by_envelope`
and returns a `ToolMessage(status="error", content=<categorizado>)` instead
of letting `langgraph.prebuilt.tool_node.ToolNode._validate_tool_call` emit
the generic `"<tool> is not a valid tool, try one of [...]"` error.

This file covers TASK 3 — `not_configured` category and the pass-through
discipline. Tasks 4/5 extend the categories.
"""
from __future__ import annotations

from typing import Any

import pytest
from langchain.agents.middleware.types import ToolCallRequest
from langchain_core.messages import ToolCall, ToolMessage

from src.agents.unified.mcp_tool_availability import (
    McpToolAvailabilityMiddleware,
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _mcp_tool_call(name: str, call_id: str = "call-1") -> ToolCallRequest:
    """Monta um `ToolCallRequest` (langchain) para uma tool call de nome
    `name` e id `call_id` — mesmo padrão usado em
    `test_envelope_middleware.py`."""
    return ToolCallRequest(
        tool_call=ToolCall(name=name, args={}, id=call_id),
        tool=None,
        state={"messages": []},
        runtime=None,  # type: ignore[arg-type]
    )


# --------------------------------------------------------------------------- #
# unit-1: not_configured — server_name unknown
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_intercepts_mcp_tool_with_not_configured_category() -> None:
    """REQ-001 (mcp-tool-availability-diagnostics): `mcp__zernio__posts_create`
    when `last_load_status.servers` is empty (no user resolved) MUST return
    a categorized `ToolMessage` with `not_configured` category, and `handler`
    MUST NOT be called (the langgraph template error never fires)."""
    middleware = McpToolAvailabilityMiddleware()
    middleware.last_load_status = {"servers": {}, "tools_by_name": {}}

    request = _mcp_tool_call("mcp__zernio__posts_create")
    handler_called = False

    async def handler(_req: ToolCallRequest) -> ToolMessage:
        nonlocal handler_called
        handler_called = True
        return ToolMessage(content="ok", name="mcp__zernio__posts_create", tool_call_id="call-1")

    result = await middleware.awrap_tool_call(request, handler)

    assert handler_called is False
    assert isinstance(result, ToolMessage)
    assert result.status == "error"
    assert result.tool_call_id == "call-1"
    assert result.name == "mcp__zernio__posts_create"
    assert result.content.startswith(
        "[Tool 'mcp__zernio__posts_create' indisponível: not_configured]"
    )
    assert "zernio" in result.content
    assert "API admin" in result.content or "admin" in result.content.lower()


# --------------------------------------------------------------------------- #
# unit-2: passes through native (no-mcp__) tools
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_passes_through_native_tools() -> None:
    """REQ-001: tool call for a native tool (no `mcp__` prefix) MUST call
    `handler(request)` and return its result unchanged — middleware MUST
    NOT inject any ToolMessage of its own."""
    middleware = McpToolAvailabilityMiddleware()
    # even with an empty last_load_status, the middleware MUST let native
    # tools through (it doesn't own native-tool gating).
    middleware.last_load_status = {"servers": {}, "tools_by_name": {}}

    request = _mcp_tool_call("read_file")
    original = ToolMessage(content="file content", name="read_file", tool_call_id="call-1")

    async def handler(_req: ToolCallRequest) -> ToolMessage:
        return original

    result = await middleware.awrap_tool_call(request, handler)

    assert result is original  # identity, not a copy
    assert result.content == "file content"
    assert result.name == "read_file"


# --------------------------------------------------------------------------- #
# unit-3: passes through valid mcp__* tool calls
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_passes_through_valid_mcp_tool_calls() -> None:
    """REQ-001: `mcp__zernio__posts_create` whose qualified name IS in
    `last_load_status.tools_by_name` MUST call `handler(request)` and
    return its result — middleware MUST NOT double-block calls whose
    target tool is in the set."""
    middleware = McpToolAvailabilityMiddleware()
    middleware.last_load_status = {
        "servers": {"zernio": {"configured": True, "connected": True, "tool_count": 2, "last_error": None}},
        "tools_by_name": {"mcp__zernio__posts_create": "zernio"},
    }

    request = _mcp_tool_call("mcp__zernio__posts_create")
    expected = ToolMessage(
        content="created",
        name="mcp__zernio__posts_create",
        tool_call_id="call-1",
        status="success",
    )

    async def handler(_req: ToolCallRequest) -> ToolMessage:
        return expected

    result = await middleware.awrap_tool_call(request, handler)

    assert result is expected
    assert result.status == "success"


# --------------------------------------------------------------------------- #
# unit-4 (task-middleware-categories-1): not_connected category
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_not_connected_with_sanitized_error_message() -> None:
    """REQ-001: quando `last_load_status.servers["zernio"]["connected"]` é
    False (servidor configurado mas falhou), `mcp__zernio__*` MUST gerar
    categoria `not_connected` com o server_name e o `last_error`
    (sanitizado) visíveis no conteúdo — sem vazar credenciais."""
    middleware = McpToolAvailabilityMiddleware()
    middleware.last_load_status = {
        "servers": {
            "zernio": {
                "configured": True,
                "connected": False,
                "tool_count": 0,
                "last_error": (
                    "McpServerConnectionError: servidor MCP 'zernio': "
                    "ConnectionRefusedError: [Errno 111] connect call failed "
                    "('127.0.0.1', 7001)"
                ),
            }
        },
        "tools_by_name": {},
    }

    request = _mcp_tool_call("mcp__zernio__posts_create")

    async def handler(_req: ToolCallRequest) -> ToolMessage:
        raise AssertionError("handler MUST NOT be called for not_connected")

    result = await middleware.awrap_tool_call(request, handler)

    assert isinstance(result, ToolMessage)
    assert result.status == "error"
    assert result.content.startswith(
        "[Tool 'mcp__zernio__posts_create' indisponível: not_connected]"
    )
    assert "zernio" in result.content
    assert "ConnectionRefusedError" in result.content


@pytest.mark.asyncio
async def test_not_connected_message_no_credential_leak() -> None:
    """REQ-001 + REQ-007 sem leak do `mcp-client`: quando o `last_error`
    carrega acidentalmente valores de `env`/`headers` (cenário adversarial
    — REQ-007 protege contra), o `ToolMessage.content` MUST NÃO conter
    nem o NOME da env var (`ZERNIO_API_KEY`, `OAUTH_TOKEN`) nem qualquer
    substring plausível de credencial."""
    middleware = McpToolAvailabilityMiddleware()
    middleware.last_load_status = {
        "servers": {
            "zernio": {
                "configured": True,
                "connected": False,
                "tool_count": 0,
                "last_error": (
                    "McpServerConnectionError: servidor MCP 'zernio': "
                    "ConnectionError: ZERNIO_API_KEY=ABCDEF-my-secret-bearer "
                    "Authorization: Bearer OAUTH_TOKEN_GHIJKL"
                ),
            }
        },
        "tools_by_name": {},
    }

    request = _mcp_tool_call("mcp__zernio__posts_create")

    async def handler(_req: ToolCallRequest) -> ToolMessage:
        raise AssertionError("handler MUST NOT be called")

    result = await middleware.awrap_tool_call(request, handler)

    assert isinstance(result, ToolMessage)
    # nem nome de env var nem valor de token
    for forbidden in (
        "ZERNIO_API_KEY",
        "ABCDEF-my-secret-bearer",
        "OAUTH_TOKEN_GHIJKL",
    ):
        assert forbidden not in result.content, (
            f"credential leak: {forbidden!r} presente em {result.content!r}"
        )


@pytest.mark.asyncio
async def test_not_configured_still_works_after_adding_not_connected() -> None:
    """regression (unit-3 do skeleton-1 replicado): após Task 4 adicionar
    `not_connected`, o caminho `not_configured` (server ausente de
    `servers`) MUST continuar disparando a categoria antiga."""
    middleware = McpToolAvailabilityMiddleware()
    middleware.last_load_status = {"servers": {}, "tools_by_name": {}}

    request = _mcp_tool_call("mcp__unknown__anything")

    async def handler(_req: ToolCallRequest) -> ToolMessage:
        raise AssertionError("handler MUST NOT be called")

    result = await middleware.awrap_tool_call(request, handler)

    assert isinstance(result, ToolMessage)
    assert result.status == "error"
    assert "not_configured" in result.content
    assert "not_connected" not in result.content


# --------------------------------------------------------------------------- #
# unit-5 (task-middleware-categories-2): unknown_tool_name category
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_unknown_tool_name_lists_real_tools_for_typo_guidance() -> None:
    """REQ-001: quando `server_name` está em `servers` com `connected=True`
    mas a `tool_name` chamada NÃO está em `tools_by_name` (typo — nome
    próximo mas não idêntico), MUST gerar `unknown_tool_name` com a
    lista das tools que o servidor REALMENTE expôs, e a substring do
    langgraph vendor `is not a valid tool` como dica de compat."""
    middleware = McpToolAvailabilityMiddleware()
    middleware.last_load_status = {
        "servers": {
            "zernio": {
                "configured": True,
                "connected": True,
                "tool_count": 2,
                "last_error": None,
            }
        },
        "tools_by_name": {
            "mcp__zernio__posts_list": "zernio",
            "mcp__zernio__posts_delete": "zernio",
        },
    }

    request = _mcp_tool_call("mcp__zernio__posts_create")  # typo

    async def handler(_req: ToolCallRequest) -> ToolMessage:
        raise AssertionError("handler MUST NOT be called")

    result = await middleware.awrap_tool_call(request, handler)

    assert isinstance(result, ToolMessage)
    assert result.status == "error"
    assert result.content.startswith(
        "[Tool 'mcp__zernio__posts_create' indisponível: unknown_tool_name]"
    )
    # server name + lista real de tools + substring langgraph (compat)
    assert "zernio" in result.content
    assert "posts_list" in result.content
    assert "posts_delete" in result.content
    # Compat hint — substring literal do langgraph vendor
    assert "is not a valid tool" in result.content


# --------------------------------------------------------------------------- #
# unit-6 (task-middleware-categories-2): filtered_by_envelope category
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_filtered_by_envelope_distinguished_from_permission_denial() -> None:
    """REQ-003 (mcp-client): quando a tool ESTÁ em
    `last_load_status.tools_by_name` (existe e está disponível no servidor)
    MAS o `EnvelopeMiddleware` filtrou ela do set final, o middleware
    MUST categorizar como `filtered_by_envelope` — explicitamente
    distinto do bloqueio genérico do envelope (mensagem diferente de
    "BLOQUEADO por capability")."""
    # Cenário: tool existe no servidor (connected=True, tools_by_name
    # tem a tool). O envelope removeu ela do set que chegou ao modelo
    # — representado aqui como uma ausência lógica: ela ESTÁ em
    # tools_by_name (estado pós-carregamento, antes do envelope), mas o
    # modelo AINDA assim não a vê no set model-bound. Como a categoria
    # só pode ser determinada via COMPARAÇÃO entre `tools_by_name` e o
    # set model-bound, o middleware precisa de um sinal explícito.
    #
    # Para Task 5, usamos uma convenção: se `tools_by_name` contém a tool
    # E o servidor está `connected=True` E o set entregue ao modelo NÃO
    # a contém (sinalizado por `last_load_status["model_bound_tools"]`
    # ausente da tool), categorizamos como `filtered_by_envelope`.
    middleware = McpToolAvailabilityMiddleware()
    middleware.last_load_status = {
        "servers": {
            "zernio": {
                "configured": True,
                "connected": True,
                "tool_count": 1,
                "last_error": None,
            }
        },
        "tools_by_name": {"mcp__zernio__posts_create": "zernio"},
        "model_bound_tools": set(),  # vazio = envelope cortou tudo de zernio
    }

    request = _mcp_tool_call("mcp__zernio__posts_create")

    async def handler(_req: ToolCallRequest) -> ToolMessage:
        raise AssertionError("handler MUST NOT be called")

    result = await middleware.awrap_tool_call(request, handler)

    assert isinstance(result, ToolMessage)
    assert result.status == "error"
    assert result.content.startswith(
        "[Tool 'mcp__zernio__posts_create' indisponível: filtered_by_envelope]"
    )
    assert "zernio" in result.content


# --------------------------------------------------------------------------- #
# unit-7 (task-integration-1): end-to-end — categorized error, not raw langgraph
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_end_to_end_intercept_before_langgraph_template() -> None:
    """REQ-001 do integration-1: usar o conjunto realista (um
    `McpToolsMiddleware` cuja `last_load_status` está populada) e
    confirmar end-to-end que o `McpToolAvailabilityMiddleware` intercepta
    ANTES do `langgraph.ToolNode._validate_tool_call` ser alcançado.
    Sem servidor MCP rodando, sem `langgraph dev` — só a unidade
    composta `McpToolsMiddleware.last_load_status →
    McpToolAvailabilityMiddleware.awrap_tool_call`.

    Contrato: a resposta do `awrap_tool_call` para uma tool MCP ausente
    do set é SEMPRE um `ToolMessage` com `status="error"` e `content`
    começando com `[Tool '<name>' indisponível: <categoria>]` —
    nunca a string literal '<tool> is not a valid tool, try one of [...]'
    como substring PRIMÁRIA (a substring langgraph pode aparecer
    dentro de `unknown_tool_name` como dica de compat — ver
    teste test_unknown_tool_name_lists_real_tools_for_typo_guidance).
    """
    middleware = McpToolAvailabilityMiddleware()
    middleware.last_load_status = {
        "loaded_at": "2026-08-05T17:00:00+00:00",
        "servers": {},  # nenhum servidor configurado
        "tools_by_name": {},
    }

    request = _mcp_tool_call("mcp__zernio__posts_create")

    async def handler(_req: ToolCallRequest) -> ToolMessage:
        # Se esta função for chamada, o middleware falhou em interceptar
        # — e o langgraph dispararia seu template genérico.
        raise AssertionError(
            "handler MUST NOT be called — middleware MUST intercept antes do "
            "ToolNode._validate_tool_call para impedir a string '<tool> is "
            "not a valid tool' de chegar ao modelo."
        )

    result = await middleware.awrap_tool_call(request, handler)

    # Garantias:
    assert isinstance(result, ToolMessage)
    assert result.status == "error"
    assert result.tool_call_id == "call-1"
    assert result.name == "mcp__zernio__posts_create"
    # 1. Mensagem categorizada
    assert result.content.startswith(
        "[Tool 'mcp__zernio__posts_create' indisponível: not_configured]"
    )
    # 2. NÃO contém a string-primária do langgraph vendor
    assert "is not a valid tool, try one of [" not in result.content, (
        f"middleware falhou em interceptar; resultado = {result.content!r}"
    )
