"""Testes de config de usage no `LangGraphDirectAgentRunner` (recording-2/5).

Cobre identidade no configurable (REQ-003). O `UsageRecordingCallback` passou
a viver no grafo (`build_unified` / `_unified_run_config`) — ver recording-5 —
para cobrir runs web sem double-record no DirectRunner.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domain.scheduling import ToolScope
from src.infrastructure.agent_runtime.langgraph_direct_runner import (
    LangGraphDirectAgentRunner,
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


@pytest.mark.asyncio
async def test_run_config_includes_user_key_and_thread_id() -> None:
    """configurable tem user_key+thread_id; callback fica no grafo, não no run."""
    fake_graph = _make_fake_graph(ainvoke_return={"messages": []})

    with (
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
    ):
        runner = LangGraphDirectAgentRunner(postgres_uri="postgresql://unused")
        await runner.run(
            thread_id="thread-abc",
            prompt="oi",
            skills=(),
            tool_scope=ToolScope.RESTRICTED,
            user_key="telegram:999",
        )

    config = _config_from_ainvoke(fake_graph)
    assert config["configurable"]["thread_id"] == "thread-abc"
    assert config["configurable"]["user_key"] == "telegram:999"
    # Callback global em build_unified — não duplicar na config do run.
    assert "callbacks" not in config


@pytest.mark.asyncio
async def test_resume_config_includes_user_key_and_thread_id() -> None:
    """Resume: mesma config de identity; callback permanece no grafo."""
    fake_graph = _make_fake_graph(ainvoke_return={"messages": []})

    with (
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
    ):
        runner = LangGraphDirectAgentRunner(postgres_uri="postgresql://unused")
        await runner.resume(
            thread_id="thread-abc",
            decisions=({"type": "approve"},),
            user_key="telegram:999",
        )

    config = _config_from_ainvoke(fake_graph)
    assert config["configurable"]["thread_id"] == "thread-abc"
    assert config["configurable"]["user_key"] == "telegram:999"
    assert "callbacks" not in config
