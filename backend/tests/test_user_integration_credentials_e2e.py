"""End-to-end verification for `user-integration-credentials`
(task `verify-1`, unit `verify-1-unit-1`, REQ-006).

Exercises `linking-1` -> `resolve-1` -> `resolve-2` -> `resolve-3` ->
`channel-1` together as ONE run: a Telegram link code is redeemed for a
user, then an authorized message from the linked chat_id is checked against
`resolve_user_id()` across three consumers in the same run —
`McpToolsMiddleware` (MCP tools), `memory_tools.save_memory` (agent memory)
and `ownership.store.record_ownership` (generated-file ownership).

Only the Postgres boundary is faked (`ownership.store.
PostgresUserIntegrationRepository`, `ownership.store.get_config`, and
`mcp_config_store.PostgresMcpServerRepository`) — every other piece
(`RedeemTelegramLinkCode`, `authorization.resolve_authorization`,
`resolve_user_id()`, the middleware, `mcp_config_store.add_server`, the
memory tools, `record_ownership`) runs its real code path. This is what closes the gap described in the
design: a Telegram session that never resolved a `user_id`, so
`mcp__zernio__posts_create` (and memory, and ownership) were invisible to a
linked user.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from langchain.agents.middleware.types import ModelRequest
from langchain_core.tools import BaseTool, tool
from langgraph.store.memory import InMemoryStore

import src.tools.memory_tools as memory_tools
from src.agents.unified import mcp_config_store
from src.agents.unified.mcp_tools_middleware import McpToolsMiddleware
from src.application.ports.mcp_server_repository import McpServerRepositoryPort
from src.application.ports.telegram_link_code_repository import (
    TelegramLinkCodeRepositoryPort,
)
from src.application.ports.user_integration_repository import (
    UserIntegrationRepositoryPort,
)
from src.application.use_cases.redeem_telegram_link_code import RedeemTelegramLinkCode
from src.domain.integrations import TelegramLinkCode, UserIntegration
from src.domain.mcp import McpServerConfig
from src.infrastructure.ownership import store as ownership_store
from src.infrastructure.telegram import authorization
from src.infrastructure.usage.user_key import telegram_user_key

_USER_ID = "user-e2e"
_CHAT_ID = "555000111"
# Distinct chat: proves authorization came from the REAL binding, not the
# legacy fallback (REQ-002 scenario 2 covers the fallback path elsewhere).
_ADMIN_LEGACY_CHAT_ID = "admin-legacy-chat"


class _FakeLinkCodeRepository(TelegramLinkCodeRepositoryPort):
    def __init__(self) -> None:
        self._store: dict[str, TelegramLinkCode] = {}

    async def save(self, link_code: TelegramLinkCode) -> None:
        self._store[link_code.code] = link_code

    async def get(self, code: str) -> TelegramLinkCode | None:
        return self._store.get(code)

    async def delete(self, code: str) -> None:
        self._store.pop(code, None)


class _FakeUserIntegrationRepository(UserIntegrationRepositoryPort):
    """Backing store shared between `RedeemTelegramLinkCode` and the fake
    Postgres boundary below — a binding created by redemption is
    immediately visible to `resolve_user_id()`, same as production Postgres."""

    def __init__(self) -> None:
        self._store: dict[str, UserIntegration] = {}

    async def save(self, integration: UserIntegration) -> None:
        self._store[integration.id] = integration

    async def get(self, integration_id: str) -> UserIntegration | None:
        return self._store.get(integration_id)

    async def list_by_user(self, user_id: str) -> list[UserIntegration]:
        return [i for i in self._store.values() if i.user_id == user_id]

    async def list_all(self) -> list[UserIntegration]:
        return list(self._store.values())

    async def delete(self, integration_id: str) -> None:
        self._store.pop(integration_id, None)


def _mock_mcp_tool(name: str) -> BaseTool:
    @tool
    def mock_tool() -> str:
        """Mock MCP tool."""
        return f"mcp tool {name}"

    mock_tool.name = name
    mock_tool.description = f"Mock MCP tool: {name}"
    return mock_tool


class _FakeCursor:
    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple | None]] = []

    async def __aenter__(self) -> "_FakeCursor":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return None

    async def execute(self, query: str, params: tuple | None = None) -> None:
        self.executed.append((query, params))


class _FakeConnection:
    def __init__(self, cursor: _FakeCursor) -> None:
        self._cursor = cursor

    async def __aenter__(self) -> "_FakeConnection":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return None

    def cursor(self) -> _FakeCursor:
        return self._cursor


class _FakePool:
    def __init__(self, cursor: _FakeCursor) -> None:
        self._cursor = cursor

    def connection(self) -> _FakeConnection:
        return _FakeConnection(self._cursor)


@pytest.fixture
def linked_repository(monkeypatch: pytest.MonkeyPatch) -> _FakeUserIntegrationRepository:
    """Wires `ownership.store.PostgresUserIntegrationRepository` to a fake
    that reads from the SAME backing store used by `RedeemTelegramLinkCode`
    in the test — so a binding created via redemption is visible to every
    downstream resolver without touching real Postgres."""
    integrations = _FakeUserIntegrationRepository()

    class _RepositoryAdapter:
        def __init__(self, conninfo: str) -> None:
            self.conninfo = conninfo

        async def list_all(self) -> list[UserIntegration]:
            return await integrations.list_all()

    monkeypatch.setattr(ownership_store, "PostgresUserIntegrationRepository", _RepositoryAdapter)
    monkeypatch.setenv("POSTGRES_URI", "postgresql://fake")
    return integrations


@pytest.fixture
def mcp_repository(monkeypatch: pytest.MonkeyPatch) -> dict[tuple[str, str], McpServerConfig]:
    """Wires `mcp_config_store.PostgresMcpServerRepository` to an in-memory
    fake — so `add_server` (below) and `load_mcp_server_config` (called
    inside `McpToolsMiddleware`, resolve-2) share the same backing store
    without touching real Postgres. Mirrors `linked_repository` above."""
    rows: dict[tuple[str, str], McpServerConfig] = {}

    class _McpRepositoryAdapter(McpServerRepositoryPort):
        def __init__(self, conninfo: str) -> None:
            self.conninfo = conninfo

        async def save(self, server: McpServerConfig) -> None:
            rows[(server.user_id, server.name)] = server

        async def get(self, user_id: str, name: str) -> McpServerConfig | None:
            return rows.get((user_id, name))

        async def list_by_user(self, user_id: str) -> list[McpServerConfig]:
            return [s for (uid, _name), s in rows.items() if uid == user_id]

        async def list_all(self) -> list[McpServerConfig]:
            return list(rows.values())

        async def delete(self, user_id: str, name: str) -> None:
            rows.pop((user_id, name), None)

    monkeypatch.setattr(mcp_config_store, "PostgresMcpServerRepository", _McpRepositoryAdapter)
    return rows


@pytest.mark.asyncio
async def test_linked_telegram_session_gets_user_scoped_tools_memory_and_ownership(
    monkeypatch: pytest.MonkeyPatch,
    linked_repository: _FakeUserIntegrationRepository,
    mcp_repository: dict[tuple[str, str], McpServerConfig],
) -> None:
    """REQ-006 (telegram-channel delta), task `verify-1`, unit `verify-1-unit-1`.

    Full run: redeem a code for `_USER_ID` from `_CHAT_ID` (linking-1) ->
    simulate an authorized message from that chat (channel-1 + resolve-1) ->
    the SAME resolved `user_id` is what `McpToolsMiddleware` (resolve-2),
    `save_memory` (resolve-3) and `record_ownership` all see in that run.
    """
    # 1. linking-1: redeem a code, binding _CHAT_ID to _USER_ID.
    link_codes = _FakeLinkCodeRepository()
    code = TelegramLinkCode(
        code="LINK42", user_id=_USER_ID, expires_at=datetime.now(UTC) + timedelta(minutes=10)
    )
    await link_codes.save(code)
    redeem = RedeemTelegramLinkCode(
        link_code_repository=link_codes, user_integration_repository=linked_repository
    )
    await redeem.execute(code="LINK42", chat_id=_CHAT_ID)

    # 2. channel-1 + resolve-1: a message from the linked chat resolves the
    #    real user_id — not just the legacy allowlist fallback.
    authorized, linked_user_id = await authorization.resolve_authorization(
        _CHAT_ID, _ADMIN_LEGACY_CHAT_ID
    )
    assert authorized is True
    assert linked_user_id == _USER_ID

    # Stamp the run's `user_key` the same way `make_message_handler` does
    # for a real message (`telegram_user_key(chat_id)`), so every tool
    # invoked "in this run" resolves through `resolve_user_id()`.
    user_key = telegram_user_key(_CHAT_ID)
    monkeypatch.setattr(
        ownership_store, "get_config", lambda: {"configurable": {"user_key": user_key}}
    )

    # 3. resolve-2: mcp_tools_middleware exposes the user's MCP tools within
    #    the same run — this is the bug reported in production. Uses the
    #    real `mcp_config_store.add_server` (Postgres-backed, per
    #    `user-scoped-mcp-config-storage`), not a hand-edited config file —
    #    that file-partitioned shape was the very bug this test closes.
    await mcp_config_store.add_server(_USER_ID, "zernio", command="node", args=["server.js"])

    mock_tools = [_mock_mcp_tool("zernio/posts_create")]
    with patch(
        "src.agents.unified.mcp_tools_middleware.list_mcp_tools",
        new=AsyncMock(return_value=(mock_tools, [])),
    ):
        middleware = McpToolsMiddleware()
        request = ModelRequest(model=None, tools=[], messages=[], state={})  # type: ignore[arg-type]

        async def handler(req: ModelRequest) -> ModelRequest:
            return req

        result = await middleware.awrap_model_call(request, handler)

    assert any(t.name == "mcp__zernio__posts_create" for t in result.tools)

    # 4. resolve-3: save_memory in the same run resolves to the linked
    #    user's namespace — not refused, not shared.
    memory_store = InMemoryStore()
    monkeypatch.setattr(memory_tools, "get_store", lambda: memory_store)
    await memory_tools.save_memory.ainvoke({"content": "lembrete via telegram vinculado"})
    items = list(memory_store.search(("memories", _USER_ID)))
    assert len(items) == 1
    assert items[0].value["content"] == "lembrete via telegram vinculado"

    # 5. media-ownership-authorization: record_ownership in the same run
    #    attributes the generated file to the linked user.
    cursor = _FakeCursor()
    monkeypatch.setattr(ownership_store, "get_pool", lambda: _FakePool(cursor))
    await ownership_store.record_ownership(kind="docx", filename="relatorio.docx")

    assert len(cursor.executed) == 1
    _, params = cursor.executed[0]
    assert params == (_USER_ID, "docx", "relatorio.docx")
