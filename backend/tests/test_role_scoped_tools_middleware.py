"""RoleScopedToolsMiddleware — session-file-sandbox task-role-1 unit tests."""
from __future__ import annotations

from typing import Any

from langchain.agents.middleware.types import ModelRequest, ToolCallRequest
from langchain_core.messages import SystemMessage, ToolCall, ToolMessage
from langchain_core.tools import tool

from src.agents.unified.role_scoped_tools_middleware import (
    USER_DEV_TOOL_DENYLIST,
    RoleScopedToolsMiddleware,
)


@tool
def git_status() -> str:
    """Git status."""
    return "clean"


@tool
def read_project_file(path: str) -> str:
    """Read a project file."""
    return f"REPO_ROOT contents of {path}"


@tool
def edit_file(path: str, content: str) -> str:
    """Edit a file."""
    return f"wrote {path}"


@tool
def run_shell_command(command: str) -> str:
    """Run shell."""
    return f"ran {command}"


@tool
def create_docx_document(title: str) -> str:
    """Create a docx."""
    return f"docx:{title}"


@tool
def approved_custom_tool(x: str) -> str:
    """Simula tool de load_approved_tools."""
    return f"approved:{x}"


def _model_request_with(tools: list[Any], *, system: str = "you are jeff") -> ModelRequest:
    return ModelRequest(
        model=None,  # type: ignore[arg-type]
        messages=[],
        system_message=SystemMessage(content=system),
        tools=tools,
    )


def _tool_names(tools: list[Any]) -> set[str]:
    names: set[str] = set()
    for t in tools:
        if isinstance(t, dict):
            names.add(t.get("name") or t.get("function", {}).get("name", ""))
        else:
            names.add(getattr(t, "name", "") or getattr(t, "__name__", ""))
    return names


def _tool_call_request(tool_name: str, call_id: str = "call-1") -> ToolCallRequest:
    return ToolCallRequest(
        tool_call=ToolCall(name=tool_name, args={}, id=call_id),
        tool=None,
        state={"messages": []},
        runtime=None,  # type: ignore[arg-type]
    )


# --- unit-1 (REQ-002): wrap_model_call omits denylist for role=user ----------


def test_wrap_model_call_omits_denylist_for_user_role() -> None:
    """WHEN role=user THEN request.tools omits USER_DEV_TOOL_DENYLIST names."""
    tools = [
        git_status,
        read_project_file,
        edit_file,
        run_shell_command,
        create_docx_document,
    ]
    mw = RoleScopedToolsMiddleware(role="user")
    captured: list[ModelRequest] = []

    def handler(request: ModelRequest) -> str:
        captured.append(request)
        return "ok"

    mw.wrap_model_call(_model_request_with(tools), handler)

    assert captured, "handler must be called"
    names = _tool_names(captured[0].tools)
    for denied in (
        "git_status",
        "read_project_file",
        "edit_file",
        "run_shell_command",
    ):
        assert denied not in names
        assert denied in USER_DEV_TOOL_DENYLIST
    assert "create_docx_document" in names


# --- unit-2 (REQ-002): wrap_tool_call blocks denylist for role=user ----------


def test_wrap_tool_call_blocks_read_project_file_for_user() -> None:
    """WHEN role=user emits wrap_tool_call for read_project_file THEN blocked."""
    mw = RoleScopedToolsMiddleware(role="user")
    recorded: list[str] = []

    def handler(request: ToolCallRequest) -> ToolMessage:
        recorded.append(request.tool_call["name"])
        # Simula vazamento de REPO_ROOT se o handler rodasse.
        return ToolMessage(
            content="REPO_ROOT contents of secret.py",
            name=request.tool_call["name"],
            tool_call_id=request.tool_call["id"],
        )

    result = mw.wrap_tool_call(
        _tool_call_request("read_project_file"),
        handler,
    )

    assert isinstance(result, ToolMessage)
    assert result.status == "error"
    assert recorded == [], "handler must not run"
    assert "REPO_ROOT" not in str(result.content)


# --- unit-3 (REQ-003): admin keeps denylist tools ----------------------------


def test_wrap_model_call_keeps_denylist_for_admin_role() -> None:
    """WHEN role=admin THEN read_project_file, git_status, run_shell_command stay."""
    tools = [
        git_status,
        read_project_file,
        edit_file,
        run_shell_command,
        create_docx_document,
    ]
    mw = RoleScopedToolsMiddleware(role="admin")
    captured: list[ModelRequest] = []

    def handler(request: ModelRequest) -> str:
        captured.append(request)
        return "ok"

    mw.wrap_model_call(_model_request_with(tools), handler)

    names = _tool_names(captured[0].tools)
    assert "read_project_file" in names
    assert "git_status" in names
    assert "run_shell_command" in names
    assert "create_docx_document" in names


# --- unit-4 (D15): approved tools omitted/blocked for non-admin --------------


def test_wrap_model_call_omits_approved_tools_for_user() -> None:
    """WHEN role=user and approved tool present THEN RoleScoped omits/blocks it."""
    tools = [create_docx_document, approved_custom_tool]
    mw = RoleScopedToolsMiddleware(
        role="user",
        approved_tool_names=frozenset({"approved_custom_tool"}),
    )
    captured: list[ModelRequest] = []

    def model_handler(request: ModelRequest) -> str:
        captured.append(request)
        return "ok"

    mw.wrap_model_call(_model_request_with(tools), model_handler)
    names = _tool_names(captured[0].tools)
    assert "approved_custom_tool" not in names
    assert "create_docx_document" in names

    recorded: list[str] = []

    def tool_handler(request: ToolCallRequest) -> ToolMessage:
        recorded.append(request.tool_call["name"])
        return ToolMessage(
            content="should-not-run",
            name=request.tool_call["name"],
            tool_call_id=request.tool_call["id"],
        )

    result = mw.wrap_tool_call(
        _tool_call_request("approved_custom_tool"),
        tool_handler,
    )
    assert isinstance(result, ToolMessage)
    assert result.status == "error"
    assert recorded == []


# --- Acceptance: REQ-005 / D10 prompt sanitization --------------------------


def test_wrap_model_call_sanitizes_user_prompt_without_repo() -> None:
    """WHEN role=user THEN system prompt omits REPO_ROOT and denylist tools."""
    repo_path = "/home/jeferson/projetos/IA/jeff_ai"
    system = (
        f"## Diretórios\n"
        f"- Repositório real: {repo_path} (código-fonte)\n"
        f"- Workspace isolado: /tmp/ws\n"
        f"## Ferramentas\n"
        f"- read_project_file e run_shell_command para o repo\n"
        f"- create_docx_document para documentos\n"
    )
    mw = RoleScopedToolsMiddleware(role="user")
    captured: list[ModelRequest] = []

    def handler(request: ModelRequest) -> str:
        captured.append(request)
        return "ok"

    mw.wrap_model_call(
        _model_request_with([create_docx_document], system=system),
        handler,
    )
    prompt = captured[0].system_message.text  # type: ignore[union-attr]
    assert "Repositório real" not in prompt
    assert "read_project_file" not in prompt
    assert "run_shell_command" not in prompt
    assert "não estão disponíveis" in prompt


# --- Acceptance: REQ-004 image_design_subagent closed set -------------------


def test_image_design_subagent_has_no_denylist_tools() -> None:
    """image_design_subagent tool set must not include USER_DEV_TOOL_DENYLIST."""
    from src.agents.subagents.image_design import image_design_subagent

    names = {
        getattr(t, "name", None) or getattr(t, "__name__", "")
        for t in image_design_subagent["tools"]
    }
    assert names.isdisjoint(USER_DEV_TOOL_DENYLIST)


# --- Acceptance: D9 middleware order in build_unified -----------------------


def test_build_unified_registers_role_scoped_after_mcp_before_envelope() -> None:
    """D9 + profile overlay: EnvelopeLifecycle → AgentProfile → McpTools* → RoleScoped → Envelope → ChatAttachment → ScopedSkills."""
    import inspect

    from src.agents.unified import agent as agent_mod

    lines = [
        ln.strip()
        for ln in inspect.getsource(agent_mod.build_unified).splitlines()
        if ln.strip()
        and not ln.strip().startswith("#")
        and not ln.strip().startswith('"""')
        and not ln.strip().startswith("`")
    ]
    # Only the create_deep_agent middleware= list entries (constructor calls).
    mw_lines = [
        ln
        for ln in lines
        if ln.startswith(
            (
                "EnvelopeLifecycleMiddleware(",
                "AgentProfileMiddleware(",
                "McpToolsMiddleware(",
                "McpToolAvailabilityMiddleware(",
                "RoleScopedToolsMiddleware(",
                "EnvelopeMiddleware(",
                "ChatAttachmentPreprocessingMiddleware(",
                "ScopedSkillsMiddleware(",
            )
        )
    ]
    # Docstring may mention EnvelopeLifecycle + Envelope once; keep the
    # trailing sequence that includes RoleScoped (the real wiring).
    role_idx = next(
        i
        for i, ln in enumerate(mw_lines)
        if ln.startswith("RoleScopedToolsMiddleware(approved_tool_names=")
    )
    seq = mw_lines[role_idx - 4 : role_idx + 4]
    expected_prefixes = [
        "EnvelopeLifecycleMiddleware(",
        "AgentProfileMiddleware(",
        "McpToolsMiddleware(",
        "McpToolAvailabilityMiddleware(",
        "RoleScopedToolsMiddleware(",
        "EnvelopeMiddleware(",
        "ChatAttachmentPreprocessingMiddleware(",
        "ScopedSkillsMiddleware(",
    ]
    assert len(seq) == 8, f"unexpected middleware neighbors: {mw_lines}"
    for line, prefix in zip(seq, expected_prefixes, strict=True):
        assert line.startswith(prefix), f"got {seq!r}"
