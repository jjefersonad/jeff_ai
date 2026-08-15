"""session-file-sandbox task-envelope-1: role ceiling on envelope grants (REQ-010)."""
from __future__ import annotations

from langchain_core.messages import ToolMessage
from langchain_core.tools import tool

from src.agents.unified.effects import Capability
from src.agents.unified.envelope_middleware import EnvelopeMiddleware
from src.agents.unified.envelope_proposal import (
    GrantDecision,
    apply_grant_to_middleware,
)


@tool
def run_shell_command(command: str) -> str:
    """Shell."""
    return f"ran:{command}"


@tool
def edit_file(path: str, content: str) -> str:
    """Edit."""
    return f"edited:{path}"


@tool
def create_docx_document(title: str) -> str:
    """Docx on the floor (write_new)."""
    return f"docx:{title}"


def _assert_blocked(mw: EnvelopeMiddleware, tool_name: str) -> None:
    from langchain.agents.middleware.types import ToolCallRequest
    from langchain_core.messages import ToolCall

    recorded: list[str] = []

    def handler(request: ToolCallRequest) -> ToolMessage:
        recorded.append(request.tool_call["name"])
        return ToolMessage(
            content="executed",
            name=request.tool_call["name"],
            tool_call_id=request.tool_call["id"],
        )

    result = mw.wrap_tool_call(
        ToolCallRequest(
            tool_call=ToolCall(name=tool_name, args={}, id="c1"),
            tool=None,
            state={"messages": [], "granted_capabilities": sorted(c.value for c in mw.granted)},
            runtime=None,  # type: ignore[arg-type]
        ),
        handler,
    )
    assert isinstance(result, ToolMessage)
    assert result.status == "error"
    assert recorded == []


def _assert_allowed(mw: EnvelopeMiddleware, tool_name: str) -> None:
    from langchain.agents.middleware.types import ToolCallRequest
    from langchain_core.messages import ToolCall

    recorded: list[str] = []

    def handler(request: ToolCallRequest) -> ToolMessage:
        recorded.append(request.tool_call["name"])
        return ToolMessage(
            content="executed",
            name=request.tool_call["name"],
            tool_call_id=request.tool_call["id"],
        )

    result = mw.wrap_tool_call(
        ToolCallRequest(
            tool_call=ToolCall(name=tool_name, args={}, id="c2"),
            tool=None,
            state={"messages": [], "granted_capabilities": sorted(c.value for c in mw.granted)},
            runtime=None,  # type: ignore[arg-type]
        ),
        handler,
    )
    assert isinstance(result, ToolMessage)
    assert result.status != "error"
    assert recorded == [tool_name]


# --- unit-1 (REQ-010): user ceiling strips shell / write_existing ------------


def test_user_grant_strips_shell_and_write_existing_keeps_floor() -> None:
    """WHEN role=user approve shell/write_existing THEN stripped; floor intact."""
    mw = EnvelopeMiddleware()
    decision = GrantDecision(
        granted_capabilities=["shell", "write_existing", "read"],
    )
    applied = apply_grant_to_middleware(decision, mw, role="user")

    assert Capability.SHELL not in applied
    assert Capability.WRITE_EXISTING not in applied
    assert Capability.SHELL not in mw.granted
    assert Capability.WRITE_EXISTING not in mw.granted

    _assert_blocked(mw, "run_shell_command")
    _assert_blocked(mw, "edit_file")
    # Floor: create_docx_document is write_new — allowed with empty/extra grant.
    _assert_allowed(mw, "create_docx_document")


# --- unit-2 (REQ-010): admin still receives shell ----------------------------


def test_admin_grant_keeps_shell() -> None:
    """WHEN role=admin grant shell THEN shell enters granted_capabilities."""
    mw = EnvelopeMiddleware()
    decision = GrantDecision(granted_capabilities=["shell", "read"])
    applied = apply_grant_to_middleware(decision, mw, role="admin")

    assert Capability.SHELL in applied
    assert Capability.SHELL in mw.granted

    from langchain.agents.middleware.types import ToolCallRequest
    from langchain_core.messages import ToolCall

    recorded: list[str] = []

    def handler(request: ToolCallRequest) -> ToolMessage:
        recorded.append(request.tool_call["name"])
        return ToolMessage(
            content="executed",
            name=request.tool_call["name"],
            tool_call_id=request.tool_call["id"],
        )

    result = mw.wrap_tool_call(
        ToolCallRequest(
            tool_call=ToolCall(name="run_shell_command", args={"command": "echo"}, id="c3"),
            tool=None,
            state={
                "messages": [],
                "granted_capabilities": sorted(c.value for c in mw.granted),
            },
            runtime=None,  # type: ignore[arg-type]
        ),
        handler,
    )
    assert isinstance(result, ToolMessage)
    assert result.status != "error"
    assert recorded == ["run_shell_command"]
