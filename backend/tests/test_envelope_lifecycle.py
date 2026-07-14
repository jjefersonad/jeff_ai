"""Integração end-to-end do ciclo propor → conceder → expirar do envelope.

Cobre a task `unified-agent-realignment-task-envelope-4` (REQ-001, REQ-002,
REQ-007 do `task-scoped-permissions`) **no grafo real**, não só nos schemas.

Diferente de `test_envelope_proposal.py` (unitário, mocka `interrupt`), aqui
construímos um `create_deep_agent` de verdade com `EnvelopeLifecycleMiddleware`
+ `EnvelopeMiddleware` + `propose_envelope_tool`, um `InMemorySaver`, e um
modelo fake que emite tool calls determinísticas. O `interrupt` real dispara,
o teste retoma com `Command(resume=...)`, e observamos:

- REQ-002: a tool de risco (`edit_file`) é BLOQUEADA antes da concessão, e
  PERMITIDA depois — e a concessão vem exclusivamente do humano (o resume).
- REQ-002: a concessão EXPIRA no turno seguinte (novo `HumanMessage` na mesma
  thread) — a tarefa B não herda o envelope da tarefa A.
- REQ-007: uma concessão cobre MÚLTIPLAS tool calls do mesmo turno (não pede
  aprovação por tool).

Estes testes são a rede de regressão da decisão de arquitetura de que o
envelope vive no **state do grafo** (per-thread, checkpointado, expira por
turno), verificada empiricamente antes da implementação.
"""
from __future__ import annotations

import itertools
from typing import Any

import pytest
from deepagents import create_deep_agent
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, ToolCall
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from src.agents.unified.envelope_middleware import (
    GRANTED_STATE_KEY,
    EnvelopeMiddleware,
)
from src.agents.unified.envelope_proposal import (
    EnvelopeLifecycleMiddleware,
    propose_envelope_tool,
)


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
class _FakeToolCallingModel(GenericFakeChatModel):
    """`GenericFakeChatModel` que aceita `bind_tools` (no-op)."""

    def bind_tools(self, tools, *, tool_choice=None, **kwargs):  # type: ignore[override]
        return self


def _model(messages: list[AIMessage]) -> _FakeToolCallingModel:
    """Modelo que emite `messages` em ordem, depois repete um AIMessage vazio."""
    tail = itertools.cycle([AIMessage(content="fim")])
    return _FakeToolCallingModel(  # type: ignore[call-arg]
        messages=itertools.chain(messages, tail),
    )


def _propose_call(cid: str = "p1") -> AIMessage:
    """AIMessage que chama `propose_envelope_tool` pedindo `write_existing`."""
    return AIMessage(
        content="",
        tool_calls=[
            ToolCall(
                name="propose_envelope",
                args={
                    "required_capabilities": [
                        {
                            "capability": "write_existing",
                            "justification": "refatorar",
                        }
                    ],
                    "excluded_capabilities": ["shell", "vcs"],
                },
                id=cid,
            )
        ],
    )


def _edit_call(cid: str, path: str = "foo.py") -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[ToolCall(name="edit_file", args={"path": path}, id=cid)],
    )


def _commit_call(cid: str, message: str = "wip") -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[ToolCall(name="git_commit", args={"message": message}, id=cid)],
    )


def _propose_call_vcs(cid: str) -> AIMessage:
    """AIMessage que chama `propose_envelope_tool` pedindo `vcs` (escalada)."""
    return AIMessage(
        content="",
        tool_calls=[
            ToolCall(
                name="propose_envelope",
                args={
                    "required_capabilities": [
                        {"capability": "vcs", "justification": "commitar"},
                    ],
                    "excluded_capabilities": [],
                },
                id=cid,
            )
        ],
    )


_EDIT_EXECUTED: list[str] = []
_COMMIT_EXECUTED: list[str] = []


@tool
def edit_file(path: str) -> str:
    """Edita um arquivo existente (write_existing). Fake para o teste."""
    _EDIT_EXECUTED.append(path)
    return f"editado {path}"


@tool
def git_commit(message: str) -> str:
    """Commita (vcs). Fake para o teste de escalada."""
    _COMMIT_EXECUTED.append(message)
    return f"commitado: {message}"


def _build_agent(model: _FakeToolCallingModel, tools: list[Any] | None = None) -> Any:
    """Monta o grafo com os DOIS middlewares do envelope + a tool de proposta."""
    return create_deep_agent(
        model=model,
        tools=tools if tools is not None else [edit_file, propose_envelope_tool],
        middleware=[EnvelopeLifecycleMiddleware(), EnvelopeMiddleware()],
        checkpointer=InMemorySaver(),
    )


@pytest.fixture(autouse=True)
def _clear_side_effects() -> Any:
    _EDIT_EXECUTED.clear()
    _COMMIT_EXECUTED.clear()
    yield
    _EDIT_EXECUTED.clear()
    _COMMIT_EXECUTED.clear()


# =========================================================================== #
# A. REQ-002: concessão humana habilita a tool; sem ela, bloqueio
# =========================================================================== #
def test_grant_enables_blocked_tool_then_expires_next_turn() -> None:
    """O ciclo completo em dois turnos na mesma thread:

    Turno 1: agente PROPÕE → humano CONCEDE `write_existing` → `edit_file`
    executa. Turno 2 (novo HumanMessage): o envelope EXPIROU → `edit_file`
    é BLOQUEADO porque a tarefa B não herdou a concessão de A (REQ-002).
    """
    agent = _build_agent(
        _model(
            [
                # Turno 1
                _propose_call("p1"),
                _edit_call("e1", "a.py"),
                AIMessage(content="turno 1 ok"),
                # Turno 2 (sem propor de novo)
                _edit_call("e2", "b.py"),
                AIMessage(content="turno 2 ok"),
            ]
        )
    )
    cfg = {"configurable": {"thread_id": "t-lifecycle"}}

    # --- Turno 1: dispara e pausa no interrupt da proposta ---
    result = agent.invoke({"messages": [("user", "refatore a.py")]}, cfg)
    assert "__interrupt__" in result, "a proposta deveria pausar via interrupt"

    # --- Humano concede `write_existing` (única via, REQ-002) ---
    agent.invoke(
        Command(
            resume={
                "granted_capabilities": ["write_existing"],
                "edited": False,
                "rejected": False,
            }
        ),
        cfg,
    )

    # `edit_file` executou no turno 1 (dentro do envelope).
    assert "a.py" in _EDIT_EXECUTED, (
        f"edit_file deveria ter executado após a concessão; "
        f"executadas={_EDIT_EXECUTED}"
    )
    state = agent.get_state(cfg)
    assert state.values.get(GRANTED_STATE_KEY) == ["write_existing"]

    # --- Turno 2: novo HumanMessage, mesma thread, SEM nova proposta ---
    agent.invoke({"messages": [("user", "agora edite b.py")]}, cfg)

    # A concessão de A NÃO foi herdada por B: `edit_file` em b.py foi
    # bloqueado (não executou).
    assert "b.py" not in _EDIT_EXECUTED, (
        "o envelope deveria ter expirado no turno 2; b.py não deveria "
        f"ter sido editado. executadas={_EDIT_EXECUTED}"
    )
    # E o state reflete o envelope zerado pelo before_agent.
    state2 = agent.get_state(cfg)
    assert state2.values.get(GRANTED_STATE_KEY) == []


# =========================================================================== #
# B. REQ-002: sem concessão, nada de risco executa
# =========================================================================== #
def test_no_grant_blocks_risky_tool() -> None:
    """Se o agente pula a proposta e chama `edit_file` direto (sem
    envelope), a tool é BLOQUEADA — enforcement no grafo, não no prompt
    (REQ-003)."""
    agent = _build_agent(
        _model(
            [
                _edit_call("e1", "sneaky.py"),
                AIMessage(content="tentou"),
            ]
        )
    )
    cfg = {"configurable": {"thread_id": "t-nogrant"}}

    agent.invoke({"messages": [("user", "edite sneaky.py sem pedir")]}, cfg)

    assert _EDIT_EXECUTED == [], (
        "edit_file sem concessão deveria ser bloqueado; "
        f"executadas={_EDIT_EXECUTED}"
    )


# =========================================================================== #
# C. REQ-007: uma concessão cobre múltiplas tool calls do mesmo turno
# =========================================================================== #
def test_one_grant_covers_many_edits_in_same_turn() -> None:
    """REQ-007: 1 concessão por tarefa, não por tool call. Uma tarefa que
    edita 3 arquivos foi aprovada UMA vez."""
    agent = _build_agent(
        _model(
            [
                _propose_call("p1"),
                _edit_call("e1", "1.py"),
                _edit_call("e2", "2.py"),
                _edit_call("e3", "3.py"),
                AIMessage(content="editei os 3"),
            ]
        )
    )
    cfg = {"configurable": {"thread_id": "t-many"}}

    result = agent.invoke({"messages": [("user", "edite 1.py, 2.py, 3.py")]}, cfg)
    assert "__interrupt__" in result

    # Uma única concessão.
    agent.invoke(
        Command(
            resume={
                "granted_capabilities": ["write_existing"],
                "edited": False,
                "rejected": False,
            }
        ),
        cfg,
    )

    assert _EDIT_EXECUTED == ["1.py", "2.py", "3.py"], (
        f"os 3 edits deveriam executar sob a mesma concessão; "
        f"executadas={_EDIT_EXECUTED}"
    )


# =========================================================================== #
# D. REQ-002: rejeição = fail-closed (nada executa)
# =========================================================================== #
def test_rejection_blocks_tool() -> None:
    """O humano rejeita a proposta → envelope vazio → `edit_file` bloqueado."""
    agent = _build_agent(
        _model(
            [
                _propose_call("p1"),
                _edit_call("e1", "x.py"),
                AIMessage(content="bloqueado"),
            ]
        )
    )
    cfg = {"configurable": {"thread_id": "t-reject"}}

    result = agent.invoke({"messages": [("user", "edite x.py")]}, cfg)
    assert "__interrupt__" in result

    agent.invoke(
        Command(
            resume={
                "granted_capabilities": [],
                "edited": False,
                "rejected": True,
            }
        ),
        cfg,
    )

    assert _EDIT_EXECUTED == [], (
        f"rejeição deveria bloquear edit_file; executadas={_EDIT_EXECUTED}"
    )
    state = agent.get_state(cfg)
    assert state.values.get(GRANTED_STATE_KEY) == []


# =========================================================================== #
# E. REQ-005: escalada mid-turn — envelope concedido some NÃO é perdido
# =========================================================================== #
def test_escalation_mid_turn_expands_envelope_without_losing_prior_grant() -> None:
    """Cenário do design: envelope sem `vcs`, usuário pede "commita agora"
    no meio da tarefa. O agente NÃO contorna (o `git_commit` bloqueado não
    "finge sucesso"), NÃO falha em silêncio — ele chama `propose_envelope`
    DE NOVO pedindo `vcs`. A segunda concessão soma ao envelope já
    concedido (`write_existing` continua valendo — não é uma tarefa nova).

    Este teste roda no GRAFO REAL (`create_deep_agent` + `InjectedState`),
    não só nos schemas — é a prova de que a escalada funciona dentro de um
    `ToolNode` de verdade, não só no harness unitário de
    `test_envelope_proposal.py`.
    """
    agent = _build_agent(
        _model(
            [
                # Turno 1: propõe write_existing, edita, tenta commitar
                # (bloqueado — vcs não está no envelope), escala pedindo
                # vcs, e finalmente commita.
                _propose_call("p1"),
                _edit_call("e1", "a.py"),
                _commit_call("c1", "primeira tentativa"),
                _propose_call_vcs("p2"),
                _commit_call("c2", "commit apos escalada"),
                AIMessage(content="feito"),
            ]
        ),
        tools=[edit_file, git_commit, propose_envelope_tool],
    )
    cfg = {"configurable": {"thread_id": "t-escalation"}}

    # --- Pausa na 1ª proposta ---
    result = agent.invoke({"messages": [("user", "refatore e commite a.py")]}, cfg)
    assert "__interrupt__" in result

    # --- Concede write_existing ---
    result = agent.invoke(
        Command(
            resume={
                "granted_capabilities": ["write_existing"],
                "edited": False,
                "rejected": False,
            }
        ),
        cfg,
    )

    # edit_file executou; a 1ª tentativa de commit foi BLOQUEADA (vcs não
    # concedido) — nenhuma tentativa de contorno, e o agente escalou.
    assert "a.py" in _EDIT_EXECUTED
    assert _COMMIT_EXECUTED == [], (
        "o 1º git_commit deveria ter sido bloqueado (vcs fora do envelope)"
    )
    # A escalada disparou um NOVO interrupt (2ª proposta no mesmo turno).
    assert "__interrupt__" in result, (
        "a escalada (2ª propose_envelope) deveria pausar de novo"
    )

    # --- Concede vcs (escalada) ---
    agent.invoke(
        Command(
            resume={
                "granted_capabilities": ["vcs"],
                "edited": False,
                "rejected": False,
            }
        ),
        cfg,
    )

    # O commit pós-escalada executou.
    assert _COMMIT_EXECUTED == ["commit apos escalada"]

    # E o envelope final do turno tem AS DUAS capabilities — a escalada
    # somou, não substituiu o que já estava concedido.
    state = agent.get_state(cfg)
    granted = set(state.values.get(GRANTED_STATE_KEY) or [])
    assert granted == {"write_existing", "vcs"}, (
        f"escalada deveria somar ao envelope prévio; granted={granted}"
    )


# =========================================================================== #
# F. Caminho ASYNC (`ainvoke`) — o `langgraph-api` real roda SEMPRE assim
# =========================================================================== #
# Todos os testes acima usam `agent.invoke()` (síncrono). O `langgraph-api`
# de produção roda o grafo via `astream()`/`ainvoke()` incondicionalmente —
# e o langchain 1.x NÃO faz bridge automático de `wrap_model_call`/
# `wrap_tool_call` (síncronos) para o contexto async: sem `awrap_model_call`/
# `awrap_tool_call` explícitos, `AgentMiddleware` levanta `NotImplementedError`
# na primeira chamada de modelo. Este teste teria pego isso — foi descoberto,
# em vez disso, testando a task `envelope-7` contra o backend real, e é
# exatamente o tipo de lacuna que este teste existe para fechar.
async def test_grant_enables_blocked_tool_via_ainvoke() -> None:
    """Mesmo cenário de `test_grant_enables_blocked_tool_then_expires_next_turn`,
    mas via `ainvoke`/`Command(resume=...)` assíncrono — o caminho real do
    `langgraph-api`."""
    agent = _build_agent(
        _model(
            [
                _propose_call("p1"),
                _edit_call("e1", "async.py"),
                AIMessage(content="feito"),
            ]
        )
    )
    cfg = {"configurable": {"thread_id": "t-async"}}

    result = await agent.ainvoke(
        {"messages": [("user", "refatore async.py")]}, cfg
    )
    assert "__interrupt__" in result, "a proposta deveria pausar via interrupt"

    await agent.ainvoke(
        Command(
            resume={
                "granted_capabilities": ["write_existing"],
                "edited": False,
                "rejected": False,
            }
        ),
        cfg,
    )

    assert "async.py" in _EDIT_EXECUTED, (
        f"edit_file deveria ter executado após a concessão (via ainvoke); "
        f"executadas={_EDIT_EXECUTED}"
    )
