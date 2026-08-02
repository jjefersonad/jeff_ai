"""Testes unitários de `LangGraphDirectAgentRunner` para a detecção de `__interrupt__`.

Cobre a task `telegram-tool-approval-task-runner-2` (REQ-001 do
`telegram-tool-approval-spec`):

- Unit 1 (interrupt presente): quando `graph.ainvoke(...)` devolve um estado
  com `__interrupt__` não-vazio carregando um `HITLRequest` (um `ActionRequest`
  e um `ReviewConfig`), o adapter devolve
  `AgentRunResult(status="interrupted", interrupt=InterruptInfo(...))`.
- Unit 2 (sem interrupt): quando `graph.ainvoke(...)` devolve um estado sem
  `__interrupt__` (ou `__interrupt__: []`), o adapter devolve
  `AgentRunResult(status="ok", interrupt=None)` — regressão guard para
  `RunScheduledTask` e `jeff_cli`.

Estes testes são PURAMENTE UNITÁRIOS: patcham `build_unified` para devolver
um fake graph + patcham os construtores async-context-manager do Postgres
para devolver mocks. Nenhum Postgres real é necessário (contraste com
`test_langgraph_direct_runner.py`, que é integração).
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.application.ports.agent_runner import AgentRunResult, InterruptInfo
from src.domain.scheduling import ToolScope
from src.infrastructure.agent_runtime.langgraph_direct_runner import (
    LangGraphDirectAgentRunner,
)


class _FakeInterrupt:
    """Imita o `langgraph.types.Interrupt` carregando um `.value` arbitrário.

    No LangGraph real, `__interrupt__` é uma tupla de `Interrupt` cujo
    `.value` é o `HITLRequest` (dataclass tipada). Aqui só precisamos de
    `.value` — o adapter (e o teste) tratam `value` como duck-typed
    via `getattr`.
    """

    def __init__(self, value: Any) -> None:  # noqa: ANN401
        self.value = value


def _make_fake_graph(ainvoke_return: Any) -> MagicMock:
    """Monta um fake `graph` cujo `ainvoke` é um `AsyncMock` que devolve
    `ainvoke_return`."""
    graph = MagicMock()
    graph.ainvoke = AsyncMock(return_value=ainvoke_return)
    return graph


@asynccontextmanager
async def _fake_pg_context():
    """Async context manager no-op que substitui
    `AsyncPostgresSaver.from_conn_string(...)` / `AsyncPostgresStore.from_conn_string(...)`.

    Os objetos devolvidos (`MagicMock()`) são ignorados — `build_unified`
    também é patchado, então o conteúdo de `saver`/`store` não importa.
    """

    yield MagicMock()


@pytest.mark.asyncio
async def test_run_returns_interrupted_when_graph_pauses_on_gated_tool() -> None:
    """Unit 1: `__interrupt__` presente → `status="interrupted"` + InterruptInfo.

    Dado um fake graph cujo `ainvoke` devolve `{"__interrupt__":
    (_FakeInterrupt(value=<HITLRequest>),)}` com um `action_request` e um
    `review_config` (o shape produzido por `HumanInTheLoopMiddleware` para
    `create_image_from_prompt`), o adapter MUST devolver
    `AgentRunResult(thread_id=<echoed>, status="interrupted", interrupt=
    InterruptInfo(action_requests=..., review_configs=...))` com os
    campos populados a partir do `HITLRequest.value`.

    RED atual: o adapter trata o retorno de `ainvoke` como sucesso silencioso
    e devolve `status="ok"`, `interrupt=None`. GREEN após a detecção.
    """
    action_request = {"name": "create_image_from_prompt", "args": {"prompt": "gato"}}
    review_config = {"allowed_decisions": ["approve", "edit", "reject"]}
    hitl_request = {
        "action_requests": (action_request,),
        "review_configs": (review_config,),
    }
    interrupt = _FakeInterrupt(value=hitl_request)
    ainvoke_return: dict[str, Any] = {"__interrupt__": (interrupt,)}

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
        ) as build_unified_mock,
    ):
        runner = LangGraphDirectAgentRunner(postgres_uri="postgresql://unused")
        result = await runner.run(
            thread_id="thread-abc",
            prompt="gere uma imagem",
            skills=(),
            tool_scope=ToolScope.RESTRICTED,
        )

    # Sanity: `build_unified` foi chamado dentro do `async with` dos checkpointer/store.
    assert build_unified_mock.call_count == 1
    # Sanity: `ainvoke` foi chamado com a config correta.
    assert fake_graph.ainvoke.call_count == 1
    call_args, call_kwargs = fake_graph.ainvoke.call_args
    assert call_args[0] == {"messages": [("user", "gere uma imagem")]}
    # `config` pode vir posicional ou keyword; o runner passa como kw, mas
    # aceitamos ambas para não acoplar o teste a esse detalhe.
    if "config" in call_kwargs:
        config = call_kwargs["config"]
    else:
        config = call_args[1]
    assert config["configurable"]["thread_id"] == "thread-abc"
    assert config["configurable"]["user_key"] == "unknown"
    # UsageRecordingCallback is graph-level (build_unified), not per-run.
    assert "callbacks" not in config

    # Requisito principal: o resultado é "interrupted" com InterruptInfo.
    assert isinstance(result, AgentRunResult)
    assert result.thread_id == "thread-abc"
    assert result.status == "interrupted"
    assert result.error is None
    assert isinstance(result.interrupt, InterruptInfo)
    assert result.interrupt.action_requests == (action_request,)
    assert result.interrupt.review_configs == (review_config,)


@pytest.mark.asyncio
async def test_run_returns_ok_with_interrupt_none_when_graph_finishes_without_interrupt() -> None:
    """Unit 2: sem `__interrupt__` → comportamento atual preservado.

    Dado um fake graph cujo `ainvoke` devolve um estado sem
    `__interrupt__` (ou `__interrupt__: []`), o adapter MUST devolver
    `AgentRunResult(thread_id=<echoed>, status="ok", error=None,
    interrupt=None)` — regressão guard para `RunScheduledTask` e
    `jeff_cli`.

    RED→GREEN: a nova branch de detecção de interrupt não pode engolir
    acidentalmente o caso "sem interrupt" (ex.: tratando lista vazia
    como truthy).
    """
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
        result = await runner.run(
            thread_id="thread-xyz",
            prompt="diga olá",
            skills=(),
            tool_scope=ToolScope.RESTRICTED,
        )

    assert isinstance(result, AgentRunResult)
    assert result.thread_id == "thread-xyz"
    assert result.status == "ok"
    assert result.error is None
    assert result.interrupt is None


@pytest.mark.asyncio
async def test_run_returns_ok_with_interrupt_none_when_interrupt_list_is_empty() -> None:
    """Unit 2 (variante): `__interrupt__: []` (lista vazia) → "ok", `interrupt=None`.

    Edge case explícito: a lista existe mas está vazia. O adapter MUST
    tratar isso como "sem pause" (igual ao caso sem a chave), não como
    "pause sem HITLRequest". RED→GREEN: protege contra uma implementação
    que verifica apenas a presença da chave (e.g. `if "__interrupt__" in
    result`) em vez da presença real de um item.
    """
    fake_graph = _make_fake_graph(ainvoke_return={"__interrupt__": ()})

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
        result = await runner.run(
            thread_id="thread-empty",
            prompt="diga olá",
            skills=(),
            tool_scope=ToolScope.RESTRICTED,
        )

    assert result.status == "ok"
    assert result.interrupt is None
    assert result.error is None
