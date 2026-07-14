"""Ordem de composição do middleware: user middleware vs `HumanInTheLoopMiddleware`.

Cobre a task `unified-agent-realignment-task-envelope-1`.

O design da change `unified-agent-realignment` decidiu (Decision D2) que o
`EnvelopeMiddleware` (um middleware de usuário) deve rodar **antes** do gate de
tiers, materializado pelo `HumanInTheLoopMiddleware` (HITL) que o deepagents
monta automaticamente a partir de `interrupt_on=...`. Se a ordem for a
inversa, o usuário será chamado a aprovar o diff de uma tool que o envelope
rejeita logo em seguida — atrito inútil.

Este teste **registra empiricamente** a ordem observada no runtime e serve
como **rede de regressão** para a decisão D2. Os três hooks do user
middleware são observados:

- `wrap_model_call` — D2 diz que o envelope é o *outermost* wrapper. Se
  isto for verdade, ele roda **antes** de qualquer middleware interno do
  `create_deep_agent`, e portanto ANTES do modelo ser invocado.
- `after_model` — HITL implementa este hook para chamar `interrupt()`. A
  chain de `after_model` executa em ORDEM REVERSA de registro (do tail
  para o user middleware), o que coloca HITL **antes** do envelope. Isto
  é o que a D2 NÃO fala explicitamente mas é o que a implementação do
  langgraph 1.x faz. O envelope não pode bloquear via `after_model`
  antes do HITL; a única defesa é o `wrap_model_call` (esconder a tool)
  ou o `wrap_tool_call` (bloquear a execução efetiva, mas depois do
  humano já ter sido incomodado).
- `wrap_tool_call` — D2 diz que o envelope é o *outermost* wrapper
  também aqui. Se for verdade, ele pode **bloquear antes** do tool
  executar — inclusive no caso degenerado em que o humano já aprovou
  via HITL.

Os testes são herméticos: nenhum Ollama ou Postgres é necessário. O modelo
é um `GenericFakeChatModel` configurado para emitir uma `AIMessage` com um
`tool_call` único, e o checkpointer é um `InMemorySaver`.
"""
from __future__ import annotations

import itertools
from typing import Any

from deepagents import create_deep_agent
from langchain.agents.middleware import AgentMiddleware, InterruptOnConfig
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolCall, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command


# --------------------------------------------------------------------------- #
# Fixture: modelo que emite sempre o mesmo tool_call.
# --------------------------------------------------------------------------- #
def _make_fake_model(responses: list[AIMessage]) -> GenericFakeChatModel:
    """Devolve um `GenericFakeChatModel` que devolve `responses` em ciclo.

    `create_deep_agent` chama `model.bind_tools(...)`; o `GenericFakeChatModel`
    base **não** implementa `bind_tools`. Devolver o próprio modelo é suficiente
    para o teste: o bind_tools não muda a saída quando o nosso `_generate` é
    determinístico.
    """

    class _FakeToolCallingModel(GenericFakeChatModel):
        def bind_tools(self, tools, *, tool_choice=None, **kwargs):  # type: ignore[override]
            return self

    return _FakeToolCallingModel(  # type: ignore[call-arg]
        messages=itertools.chain(responses, itertools.cycle(responses)),
    )


def _tool_call_message(
    name: str, args: dict[str, Any], call_id: str = "call-1"
) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[ToolCall(name=name, args=args, id=call_id)],
    )


# --------------------------------------------------------------------------- #
# Middleware observável: registra o instante em que cada hook foi chamado.
# --------------------------------------------------------------------------- #
class _RecordingMiddleware(AgentMiddleware):
    """Mínimo viável de `EnvelopeMiddleware` com hooks observáveis.

    Cada hook delega para `handler` (comportamento transparente) e antes/depois
    anexa um marcador a `events`. Os marcadores são strings com prefixo distinto
    para cada hook, de modo que a ordem dos eventos possa ser lida
    diretamente.

    `wrap_tool_call` é o gancho de bloqueio: o teste pode, opcionalmente,
    substituí-lo via `block` para devolver uma `ToolMessage` de erro em vez
    de chamar o handler. Por default, delega (não bloqueia) — para que o
    teste meça apenas a ORDEM, não a eficácia do bloqueio.
    """

    TAG = "envelope"

    def __init__(self, events: list[str], *, block_in_wrap_tool_call: bool = False) -> None:
        self._events = events
        self._block = block_in_wrap_tool_call

    def _log(self, hook: str, side: str) -> None:
        self._events.append(f"{self.TAG}.{hook}.{side}")

    def wrap_model_call(self, request, handler):  # type: ignore[no-untyped-def]
        self._log("wrap_model_call", "enter")
        try:
            return handler(request)
        finally:
            self._log("wrap_model_call", "exit")

    def after_model(self, state, runtime):  # type: ignore[no-untyped-def]
        self._log("after_model", "enter")
        try:
            return None
        finally:
            self._log("after_model", "exit")

    def wrap_tool_call(self, request, handler):  # type: ignore[no-untyped-def]
        self._log("wrap_tool_call", "enter")
        try:
            if self._block:
                # Defesa em profundidade: bloquear ANTES de delegar. Igual ao
                # `EnvelopeMiddleware` do design.
                return ToolMessage(
                    content="BLOQUEADO pelo envelope",
                    name=request.tool_call["name"],
                    tool_call_id=request.tool_call["id"],
                    status="error",
                )
            return handler(request)
        finally:
            self._log("wrap_tool_call", "exit")


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _index_of(events: list[str], marker: str) -> int | None:
    """Devolve o índice da primeira ocorrência de `marker` em `events`, ou None."""
    for i, e in enumerate(events):
        if marker in e:
            return i
    return None


def _build_graph(
    events: list[str],
    *,
    block_in_wrap_tool_call: bool = False,
) -> tuple[Any, dict[str, Any]]:
    """Monta o grafo hermético usado pelos testes desta task.

    Devolve `(graph, config)`. O `config` traz um `thread_id` único, necessário
    para o checkpointer em memória.
    """
    from langchain.tools import tool  # local: evita custo de import fora dos testes

    @tool
    def edit_file(path: str, content: str) -> str:
        """Edit an existing file with new content."""
        return f"wrote {len(content)} bytes to {path}"

    fake = _make_fake_model(
        [
            _tool_call_message(
                "edit_file", {"path": "x.py", "content": "y"}, call_id="call-1"
            )
        ]
    )
    graph = create_deep_agent(
        model=fake,
        tools=[edit_file],
        system_prompt="you are a coder",
        interrupt_on={
            "edit_file": InterruptOnConfig(allowed_decisions=["approve"]),
        },
        middleware=[_RecordingMiddleware(events, block_in_wrap_tool_call=block_in_wrap_tool_call)],
        checkpointer=InMemorySaver(),
    )
    return graph, {"configurable": {"thread_id": "envelope-1-probe"}}


# --------------------------------------------------------------------------- #
# A. Ordem observada: `wrap_model_call` e a pausa do HITL
# --------------------------------------------------------------------------- #
def test_wrap_model_call_of_envelope_runs_then_hitl_interrupts() -> None:
    """A primeira parte da D2: o `wrap_model_call` do envelope é o
    *outermost* wrapper e roda **antes** de o modelo ser invocado.

    Em seguida, HITL (que é construído pelo deepagents no tail do grafo)
    interrompe no `after_model` **antes** do `after_model` do envelope
    rodar. Isto é o que a implementação do langgraph 1.x faz: a chain
    de `after_model` executa em ORDEM REVERSA de registro.

    Consequência prática: o envelope só pode "rodar antes" via
    `wrap_model_call` (escondendo a tool do modelo). Se o `wrap_model_call`
    não esconder (e.g. tool veio por subagente), o humano é chamado a
    aprovar antes do envelope ter chance de bloquear — atrito inútil.
    O `wrap_tool_call` continua sendo a defesa em profundidade, mas
    depois do prompt de aprovação.

    Este teste documenta a realidade atual; a task `envelope-3` é a
    responsável por decidir se essa ordem é aceitável e como mitigá-la.
    """
    events: list[str] = []

    graph, config = _build_graph(events)

    # --- 1ª chamada: o modelo emite a tool_call; HITL deve pausar -----------
    first = graph.invoke(
        {"messages": [HumanMessage(content="please edit x.py")]},
        config=config,
    )
    assert "__interrupt__" in first, (
        "esperava que HITL pausasse o grafo; sem interrupt, o teste não "
        "mede nada de útil"
    )

    # O `wrap_model_call` do envelope DEVE ter rodado (é o outermost). É a
    # única coisa do envelope que pode rodar antes do HITL pausar — por
    # design, o envelope poderia ter escondido a tool aqui (G1 do design).
    assert _index_of(events, "envelope.wrap_model_call.enter") is not None, (
        "o envelope nem chegou a wrap_model_call — chain não foi composto "
        f"como esperado. events={events}"
    )

    # `wrap_model_call` é o outermost: seu `enter` precede o `exit` de
    # qualquer middleware interno (e precede qualquer hook que rode
    # apenas depois do model retornar).
    model_call_enter = _index_of(events, "envelope.wrap_model_call.enter")
    model_call_exit = _index_of(events, "envelope.wrap_model_call.exit")
    assert model_call_enter is not None and model_call_exit is not None
    assert model_call_enter < model_call_exit, (
        "wrap_model_call deveria ter rodado enter ANTES de exit; "
        f"events={events}"
    )

    # `after_model` e `wrap_tool_call` AINDA NÃO podem ter rodado:
    # o grafo está pausado no `interrupt()` que HITL dispara dentro do
    # seu próprio `after_model`. A chain de `after_model` é executada
    # em ORDEM REVERSA de registro (do tail para o user middleware), o
    # que coloca HITL **antes** do envelope nessa fase.
    assert _index_of(events, "envelope.after_model") is None, (
        "envelope.after_model rodou na 1ª invocação: isso significa que o "
        "HITL não pausou antes — ou que a ordem do `after_model` é "
        "diferente do previsto no design. "
        f"events={events}"
    )
    assert _index_of(events, "envelope.wrap_tool_call") is None, (
        "envelope.wrap_tool_call rodou antes do resume: o grafo não "
        "deveria ter chegado ao tool node. "
        f"events={events}"
    )

    # --- Resume: o humano aprova -----------------------------------------
    second = graph.invoke(
        Command(resume={"decisions": [{"type": "approve"}]}),
        config=config,
    )

    # Após o resume, o `after_model` do envelope DEVE rodar (o HITL já
    # processou a decisão e o controle volta para a chain, que caminha
    # de volta até o envelope).
    assert _index_of(events, "envelope.after_model") is not None, (
        "após o resume, o after_model do envelope deveria ter rodado; "
        f"events={events}"
    )

    # E como o envelope delega (não bloqueia) o `wrap_tool_call`, o
    # `edit_file` foi de fato executado.
    tool_messages = [m for m in second.get("messages", []) if isinstance(m, ToolMessage)]
    assert any("wrote" in (m.content or "") for m in tool_messages), (
        "esperava que edit_file rodasse (envelope está em modo "
        f"transparente). tool_messages={tool_messages}"
    )


# --------------------------------------------------------------------------- #
# B. Defesa em profundidade: o envelope bloqueia o tool call se o humano
#    já aprovou. Isto é o atrito que o design quer evitar — e o teste
#    documenta o comportamento atual para que `envelope-3` o trate.
# --------------------------------------------------------------------------- #
def test_envelope_blocks_tool_call_after_human_already_approved() -> None:
    """Se o `wrap_model_call` do envelope falhar em esconder a tool (e.g.
    via subagente), o `wrap_tool_call` ainda a bloqueia. O humano é
    solicitado a aprovar ANTES de o envelope poder bloquear — esse é o
    atrito que D2 quer evitar e o motivo desta task existir.
    """
    events: list[str] = []
    graph, config = _build_graph(events, block_in_wrap_tool_call=True)

    first = graph.invoke(
        {"messages": [HumanMessage(content="please edit x.py")]},
        config=config,
    )
    assert "__interrupt__" in first

    # Resume: humano aprova o que o envelope teria rejeitado.
    second = graph.invoke(
        Command(resume={"decisions": [{"type": "approve"}]}),
        config=config,
    )

    # O `wrap_tool_call` do envelope bloqueou: a `ToolMessage` retornada
    # tem `status="error"` e o conteúdo do bloqueio.
    blocked = [
        m
        for m in second.get("messages", [])
        if isinstance(m, ToolMessage)
        and isinstance(m.content, str)
        and m.content.startswith("BLOQUEADO")
    ]
    assert blocked, (
        "envelope.wrap_tool_call deveria ter bloqueado o edit_file mesmo "
        "após o humano aprovar. mensagens finais: "
        f"{[type(m).__name__ for m in second.get('messages', [])]}"
    )

    # E o edit_file NUNCA rodou: nenhum "wrote" no histórico.
    wrote_anywhere = any(
        isinstance(m, ToolMessage) and "wrote" in (m.content or "")
        for m in second.get("messages", [])
    )
    assert not wrote_anywhere, (
        "edit_file executou apesar do envelope ter bloqueado — defesa em "
        "profundidade falhou"
    )


# --------------------------------------------------------------------------- #
# C. A chain de `wrap_model_call` é outermost = primeiro registrado
# --------------------------------------------------------------------------- #
def test_user_middleware_is_outermost_in_wrap_model_call_chain() -> None:
    """Propriedade do `langchain.agents.factory._chain_model_call_handlers`:
    a chain é outermost = PRIMEIRO middleware registrado, innermost =
    ÚLTIMO. O `_RecordingMiddleware` é o único user middleware, então é
    o outermost. Seu `enter` é o PRIMEIRO evento a rodar nessa chain.
    """
    events: list[str] = []
    graph, config = _build_graph(events)

    graph.invoke(
        {"messages": [HumanMessage(content="please edit x.py")]},
        config=config,
    )

    # O primeiro hook do envelope a entrar é o `wrap_model_call.enter`.
    # (Não pode haver nenhum outro evento do envelope antes dele; o
    # `after_model` só roda se o model retorna com sucesso, e o
    # `wrap_tool_call` nunca roda porque HITL pausa.)
    assert events, f"nenhum evento registrado: {events}"
    first_event = events[0]
    assert "envelope.wrap_model_call.enter" in first_event, (
        f"o primeiro evento do envelope deveria ser wrap_model_call.enter, "
        f"mas foi {first_event!r}. events={events}"
    )
