"""`RoleScopedToolsMiddleware` — filtra tools por `configurable.role`.

Decision D3/D9/D10/D15 da change `session-file-sandbox`:
- `wrap_model_call` omite `USER_DEV_TOOL_DENYLIST` (+ approved tools) para
  non-admin e sanitiza o system prompt (sem `REPO_ROOT` / denylist).
- `wrap_tool_call` bloqueia as mesmas tools mesmo se ainda existirem no
  ToolNode (defesa em profundidade).
- Admin passa transparente.
"""
from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ModelRequest, ToolCallRequest
from langchain_core.messages import SystemMessage, ToolMessage
from langchain_core.tools import BaseTool
from langgraph.types import Command

try:
    from langgraph.config import get_config
except ImportError:  # pragma: no cover
    def get_config() -> dict[str, Any]:  # type: ignore[misc]
        return {}

_log = logging.getLogger(__name__)

# Spec role-scoped-agent-tools REQ-002 — denylist canônica para role=user.
USER_DEV_TOOL_DENYLIST: frozenset[str] = frozenset(
    {
        "list_project_files",
        "read_project_file",
        "grep_project",
        "edit_file",
        "patch_file",
        "multi_file_edit",
        "git_status",
        "git_diff",
        "git_commit",
        "git_apply_commit",
        "git_branch",
        "run_shell_command",
        "run_tests",
        "save_generated_tool",
        "list_generated_tools",
        "find_external_skills",
        "list_skills_in_repo",
        "install_external_skill",
        "create_feature_directory",
        "load_template",
        "validate_artifact",
        "get_sdd_state",
        "get_next_feature_number",
        "merge_generated_files",
    }
)

_BLOCK_TEMPLATE = (
    "Tool '{tool_name}' is not available for this session role. "
    "Repository / shell / git tools are admin-only."
)

_USER_PROMPT_NOTE = (
    "\n\n## Disponibilidade de código\n"
    "Edição de código, git, shell e leitura do repositório do produto "
    "não estão disponíveis nesta sessão. Use as tools de produto "
    "(documentos, imagens, memória, busca, e-mail, CRM, agenda).\n"
)


def _tool_name(tool: BaseTool | dict[str, Any]) -> str:
    if isinstance(tool, dict):
        return str(tool.get("name") or tool.get("function", {}).get("name") or "")
    return str(getattr(tool, "name", "") or getattr(tool, "__name__", "") or "")


def _resolve_role_from_config() -> str:
    """Fail-closed: identidade irresolvível ⇒ user (nunca admin por omissão)."""
    try:
        configurable = get_config().get("configurable", {}) or {}
    except Exception:  # noqa: BLE001 — fora de runnable context
        return "user"
    role = configurable.get("role")
    if role == "admin":
        return "admin"
    return "user"


class RoleScopedToolsMiddleware(AgentMiddleware[Any, Any, Any]):
    """Omite/bloqueia tools de repo/dev (e approved generated) para non-admin."""

    def __init__(
        self,
        *,
        role: str | None = None,
        approved_tool_names: frozenset[str] | Sequence[str] | None = None,
        block_message: str = _BLOCK_TEMPLATE,
    ) -> None:
        super().__init__()
        self._role_override = role
        self._approved_tool_names = frozenset(approved_tool_names or ())
        self._block_template = block_message
        self.blocked_calls: list[str] = []

    def _role(self) -> str:
        if self._role_override is not None:
            return "admin" if self._role_override == "admin" else "user"
        return _resolve_role_from_config()

    def _blocked_names(self) -> frozenset[str]:
        return USER_DEV_TOOL_DENYLIST | self._approved_tool_names

    def _is_blocked(self, name: str) -> bool:
        if self._role() == "admin":
            return False
        return name in self._blocked_names()

    def _filter_tools(
        self, tools: Sequence[BaseTool | dict[str, Any]]
    ) -> list[BaseTool | dict[str, Any]]:
        if self._role() == "admin":
            return list(tools)
        blocked = self._blocked_names()
        return [t for t in tools if _tool_name(t) not in blocked]

    def _sanitize_system_message(
        self, system_message: SystemMessage | None
    ) -> SystemMessage | None:
        if self._role() == "admin" or system_message is None:
            return system_message
        text = system_message.text if hasattr(system_message, "text") else str(
            system_message.content
        )
        # REQ-005 / D10: não anunciar REPO_ROOT nem tools da denylist.
        lines: list[str] = []
        for line in text.splitlines():
            lower = line.lower()
            if "repositório real" in lower or "repositorio real" in lower:
                continue
            if any(name in line for name in USER_DEV_TOOL_DENYLIST):
                continue
            # Evita path absoluto típico do REPO_ROOT no bloco de diretórios.
            if "/jeff_ai" in line and "código-fonte" in line.lower():
                continue
            lines.append(line)
        sanitized = "\n".join(lines).rstrip() + _USER_PROMPT_NOTE
        return SystemMessage(content=sanitized)

    def _filtered_model_request(self, request: ModelRequest) -> ModelRequest:
        filtered_tools = self._filter_tools(request.tools)
        system_message = self._sanitize_system_message(request.system_message)
        return request.override(tools=filtered_tools, system_message=system_message)

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Any],
    ) -> Any:
        return handler(self._filtered_model_request(request))

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Any],
    ) -> Any:
        return await handler(self._filtered_model_request(request))

    def _evaluate_tool_call(self, request: ToolCallRequest) -> ToolMessage | None:
        tool_name = request.tool_call.get("name", "")
        tool_call_id = request.tool_call.get("id", "")
        if not self._is_blocked(tool_name):
            return None
        if tool_call_id:
            self.blocked_calls.append(tool_call_id)
        _log.info(
            "role_scoped_block tool=%r role=%r tool_call_id=%r",
            tool_name,
            self._role(),
            tool_call_id,
        )
        return ToolMessage(
            content=self._block_template.format(tool_name=tool_name),
            name=tool_name,
            tool_call_id=tool_call_id,
            status="error",
        )

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command[Any]],
    ) -> ToolMessage | Command[Any]:
        blocked = self._evaluate_tool_call(request)
        if blocked is not None:
            return blocked
        return handler(request)

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Any],
    ) -> ToolMessage | Command[Any]:
        blocked = self._evaluate_tool_call(request)
        if blocked is not None:
            return blocked
        return await handler(request)


__all__ = [
    "USER_DEV_TOOL_DENYLIST",
    "RoleScopedToolsMiddleware",
]
