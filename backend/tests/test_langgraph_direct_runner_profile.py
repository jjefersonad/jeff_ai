"""Stamp de `profile_id` no DirectRunner (runtime-4 / REQ-005).

Interactive (Telegram/WhatsApp/CLI via `use_default_profile=True`) sem
`profile_id` explícito usa `get_default(user_id)`. Caminho do scheduler
passa `profile_id` explícito e NÃO chama `get_default`. Default
`profile_id=None` + `use_default_profile=False` preserva callers atuais
(tasks agendadas continuam overlay no-op até sched-2).
"""
from __future__ import annotations

import inspect
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.application.ports.agent_runner import AgentRunnerPort
from src.domain.agents import AgentProfile
from src.domain.scheduling import ToolScope
from src.infrastructure.agent_runtime import langgraph_direct_runner as runner_mod
from src.infrastructure.agent_runtime.langgraph_direct_runner import (
    LangGraphDirectAgentRunner,
    _build_run_config,
)


def _profile(
    *,
    profile_id: str,
    user_id: str = "user-1",
    archived_at: datetime | None = None,
) -> AgentProfile:
    now = datetime.now(UTC)
    return AgentProfile(
        id=profile_id,
        user_id=user_id,
        name="Coder",
        slug="coder",
        system_prompt="x",
        archived_at=archived_at,
        created_at=now,
        updated_at=now,
    )


def _make_fake_graph(ainvoke_return: Any) -> MagicMock:
    graph = MagicMock()
    graph.ainvoke = AsyncMock(return_value=ainvoke_return)
    return graph


@asynccontextmanager
async def _fake_pg_context():
    yield MagicMock()


def _config_from_ainvoke(fake_graph: MagicMock) -> dict[str, Any]:
    call_args, call_kwargs = fake_graph.ainvoke.call_args
    if "config" in call_kwargs:
        return call_kwargs["config"]
    return call_args[1]


def _patch_runner(fake_graph: MagicMock):
    return (
        patch(
            "src.infrastructure.agent_runtime.langgraph_direct_runner"
            ".AsyncPostgresSaver.from_conn_string",
            return_value=_fake_pg_context(),
        ),
        patch(
            "src.infrastructure.agent_runtime.langgraph_direct_runner"
            ".AsyncPostgresStore.from_conn_string",
            return_value=_fake_pg_context(),
        ),
        patch(
            "src.infrastructure.agent_runtime.langgraph_direct_runner.build_unified",
            return_value=fake_graph,
        ),
        patch(
            "src.infrastructure.agent_runtime.langgraph_direct_runner"
            ".resolve_role_for_user_key",
            new=AsyncMock(return_value="user"),
        ),
    )


def test_build_run_config_stamps_explicit_profile_id() -> None:
    """Caminho do scheduler: profile_id explícito entra no configurable."""
    config = _build_run_config(
        thread_id="t1",
        user_key="web:owner-1",
        profile_id="task-profile-id",
    )
    assert config["configurable"]["profile_id"] == "task-profile-id"


def test_build_run_config_omits_profile_id_when_none() -> None:
    config = _build_run_config(thread_id="t1", user_key="web:owner-1")
    assert "profile_id" not in config["configurable"]


def test_agent_runner_port_run_accepts_optional_profile_id() -> None:
    sig = inspect.signature(AgentRunnerPort.run)
    assert "profile_id" in sig.parameters
    assert sig.parameters["profile_id"].default is None


@pytest.mark.asyncio
async def test_interactive_run_without_profile_id_stamps_get_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WHEN run interativo sem profile_id e o user tem perfis THEN carimba get_default."""
    default = _profile(profile_id="oldest-active", user_id="user-1")
    get_default_calls: list[str] = []

    async def _user_id(user_key: str | None) -> str | None:
        assert user_key == "telegram:999"
        return "user-1"

    async def _get_default(user_id: str) -> AgentProfile | None:
        get_default_calls.append(user_id)
        return default

    monkeypatch.setattr(runner_mod, "_user_id_from_user_key", _user_id, raising=False)
    monkeypatch.setattr(runner_mod, "_get_default_profile", _get_default, raising=False)

    fake_graph = _make_fake_graph(ainvoke_return={"messages": []})
    patches = _patch_runner(fake_graph)
    with patches[0], patches[1], patches[2], patches[3]:
        runner = LangGraphDirectAgentRunner(postgres_uri="postgresql://unused")
        await runner.run(
            thread_id="thread-abc",
            prompt="oi",
            skills=(),
            tool_scope=ToolScope.RESTRICTED,
            user_key="telegram:999",
            use_default_profile=True,
        )

    config = _config_from_ainvoke(fake_graph)
    assert config["configurable"]["profile_id"] == "oldest-active"
    assert get_default_calls == ["user-1"]


@pytest.mark.asyncio
async def test_explicit_profile_id_is_stamped_without_get_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WHEN profile_id é passado explicitamente THEN esse id é carimbado (scheduler)."""
    get_default_calls: list[str] = []

    async def _get_default(user_id: str) -> AgentProfile | None:
        get_default_calls.append(user_id)
        return _profile(profile_id="should-not-use")

    async def _lookup(user_id: str, profile_id: str) -> AgentProfile | None:
        return _profile(profile_id=profile_id, user_id="owner-1")

    monkeypatch.setattr(runner_mod, "_get_default_profile", _get_default, raising=False)
    monkeypatch.setattr(runner_mod, "_lookup_agent_profile", _lookup, raising=False)

    fake_graph = _make_fake_graph(ainvoke_return={"messages": []})
    patches = _patch_runner(fake_graph)
    with patches[0], patches[1], patches[2], patches[3]:
        runner = LangGraphDirectAgentRunner(postgres_uri="postgresql://unused")
        await runner.run(
            thread_id="thread-abc",
            prompt="oi",
            skills=(),
            tool_scope=ToolScope.RESTRICTED,
            user_key="web:owner-1",
            profile_id="scheduled-profile-id",
        )

    config = _config_from_ainvoke(fake_graph)
    assert config["configurable"]["profile_id"] == "scheduled-profile-id"
    assert config["configurable"]["tool_scope"] == "restricted"
    assert get_default_calls == []


@pytest.mark.asyncio
async def test_null_profile_id_does_not_call_get_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WHEN scheduler omits profile_id THEN overlay is no-op even if a default exists."""
    get_default_calls: list[str] = []

    async def _get_default(user_id: str) -> AgentProfile | None:
        get_default_calls.append(user_id)
        return _profile(profile_id="oldest-active")

    monkeypatch.setattr(runner_mod, "_get_default_profile", _get_default, raising=False)

    fake_graph = _make_fake_graph(ainvoke_return={"messages": []})
    patches = _patch_runner(fake_graph)
    with patches[0], patches[1], patches[2], patches[3]:
        runner = LangGraphDirectAgentRunner(postgres_uri="postgresql://unused")
        await runner.run(
            thread_id="thread-abc",
            prompt="oi",
            skills=(),
            tool_scope=ToolScope.RESTRICTED,
            user_key="web:owner-1",
        )

    config = _config_from_ainvoke(fake_graph)
    assert "profile_id" not in config["configurable"]
    assert get_default_calls == []


@pytest.mark.asyncio
async def test_archived_explicit_profile_fails_without_get_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WHEN the stamped profile is archived THEN the run errors and skips get_default."""
    get_default_calls: list[str] = []

    async def _get_default(user_id: str) -> AgentProfile | None:
        get_default_calls.append(user_id)
        return _profile(profile_id="oldest-active")

    async def _lookup(user_id: str, profile_id: str) -> AgentProfile | None:
        return _profile(
            profile_id=profile_id,
            user_id=user_id,
            archived_at=datetime.now(UTC),
        )

    monkeypatch.setattr(runner_mod, "_get_default_profile", _get_default, raising=False)
    monkeypatch.setattr(runner_mod, "_lookup_agent_profile", _lookup, raising=False)

    fake_graph = _make_fake_graph(ainvoke_return={"messages": []})
    patches = _patch_runner(fake_graph)
    with patches[0], patches[1], patches[2], patches[3]:
        runner = LangGraphDirectAgentRunner(postgres_uri="postgresql://unused")
        result = await runner.run(
            thread_id="thread-abc",
            prompt="oi",
            skills=(),
            tool_scope=ToolScope.RESTRICTED,
            user_key="web:owner-1",
            profile_id="archived-id",
        )

    assert result.status == "error"
    assert result.error is not None
    assert "profile_id" in result.error
    assert get_default_calls == []
    fake_graph.ainvoke.assert_not_called()


def test_build_run_config_stamps_tool_scope() -> None:
    """Fire-time: DirectRunner carimba tool_scope para intersectar o overlay."""
    config = _build_run_config(
        thread_id="t1",
        user_key="web:owner-1",
        profile_id="p-coder",
        tool_scope=ToolScope.FULL,
    )
    assert config["configurable"]["tool_scope"] == "full"
