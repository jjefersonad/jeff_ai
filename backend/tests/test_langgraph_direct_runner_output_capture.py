"""Testes da captura de texto do output do agente em `LangGraphDirectAgentRunner`.

Cobre a task `unify-message-delivery-pipeline-task-capture-1` (spec
`agent-output-capture`):

- REQ-001: último item de `state["messages"]` é `AIMessage` com
  `tool_calls=[]` → `result.output.text` é o conteúdo dessa mensagem.
- REQ-001: último item não é `AIMessage` (ex.: `ToolMessage`) →
  `result.output.text is None`.
- REQ-004: `state["messages"]` malformado (`None`) → a captura engole a
  exceção, loga WARNING, `output` fica `None`, `result.status` não é afetado.

Puramente unitário — mesmo padrão de mocking de
`test_langgraph_direct_runner_interrupt.py`: patcha `build_unified` e os
context managers do Postgres, sem tocar banco real.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, ToolMessage

from src.application.ports.agent_runner import AgentRunOutcome
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


async def _run_with_fake_state(ainvoke_return: Any):
    fake_graph = _make_fake_graph(ainvoke_return)

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
        return await runner.run(
            thread_id="thread-capture",
            prompt="oi",
            skills=(),
            tool_scope=ToolScope.RESTRICTED,
        )


@pytest.mark.asyncio
async def test_last_ai_message_becomes_output_text() -> None:
    ai_message = AIMessage(content="Olá! Sou o Jeff AI...", tool_calls=[])
    result = await _run_with_fake_state({"messages": [ai_message]})

    assert result.status == "ok"
    assert isinstance(result.output, AgentRunOutcome)
    assert result.output.text == "Olá! Sou o Jeff AI..."


@pytest.mark.asyncio
async def test_last_message_not_ai_message_yields_output_text_none() -> None:
    tool_message = ToolMessage(content="resultado da tool", tool_call_id="call-1")
    result = await _run_with_fake_state({"messages": [tool_message]})

    assert result.status == "ok"
    assert isinstance(result.output, AgentRunOutcome)
    assert result.output.text is None


@pytest.mark.asyncio
async def test_malformed_messages_state_is_fail_safe(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level("WARNING"):
        result = await _run_with_fake_state({"messages": None})

    assert result.status == "ok"
    assert result.output is None
    assert any("output_capture_failed" in record.message for record in caplog.records)
