"""Testes do ciclo `propor → conceder → expirar` do envelope.

Cobre a task `unified-agent-realignment-task-envelope-4` (REQ-001,
REQ-002, REQ-007 do `task-scoped-permissions`). O ciclo é:

1. Agente propõe um envelope estruturado (`ProposeEnvelope`).
2. Humano concede (ou edita) — `GrantDecision`.
3. Envelope é aplicado ao `EnvelopeMiddleware` para o turno.
4. Envelope expira no próximo turno (Q7: turno = do `HumanMessage`
   ao `AIMessage` final sem tool calls).

Os testes são unitários: validam o schema, a função de aplicação
do grant, e o comportamento do tool `propose_envelope_tool` com
`interrupt()`.
"""
from __future__ import annotations

import json
from typing import Any

import pytest
from pydantic import ValidationError

from src.agents.unified.effects import Capability
from src.agents.unified.envelope_middleware import EnvelopeMiddleware
from src.agents.unified.envelope_proposal import (
    PROPOSE_ENVELOPE_TOOL_NAME,
    CapabilityProposal,
    GrantDecision,
    ProposeEnvelope,
    apply_grant_to_middleware,
    compute_approval_rate,
    propose_envelope_tool,
)


# =========================================================================== #
# A. REQ-001: ProposeEnvelope é um schema estruturado (não texto livre)
# =========================================================================== #
def test_propose_envelope_is_pydantic_model() -> None:
    """A proposta é um objeto Pydantic validável, não texto livre."""
    assert issubclass(ProposeEnvelope, object)
    # Tem os campos esperados.
    assert "required_capabilities" in ProposeEnvelope.model_fields
    assert "excluded_capabilities" in ProposeEnvelope.model_fields


def test_propose_envelope_with_valid_capabilities() -> None:
    """Caso feliz: proposta válida com capabilities requeridas e excluídas."""
    proposal = ProposeEnvelope(
        required_capabilities=[
            {"capability": "read", "justification": "Ler o código antes"},
            {
                "capability": "write_existing",
                "justification": "Refatorar a função X",
            },
        ],
        excluded_capabilities=["shell", "vcs"],
    )

    assert len(proposal.required_capabilities) == 2
    assert proposal.to_required_set() == {
        Capability.READ,
        Capability.WRITE_EXISTING,
    }
    assert proposal.to_excluded_set() == {Capability.SHELL, Capability.VCS}


def test_propose_envelope_rejects_unknown_capability() -> None:
    """Capability desconhecida do enum é rejeitada (Pydantic)."""
    with pytest.raises(ValidationError) as exc_info:
        ProposeEnvelope(
            required_capabilities=[
                {"capability": "definitely_not_a_capability", "justification": "x"},
            ],
        )
    assert "definitely_not_a_capability" in str(exc_info.value)


def test_propose_envelope_requires_justification() -> None:
    """Justificativa é obrigatória (REQ-001: '1 linha por capability')."""
    with pytest.raises(ValidationError):
        ProposeEnvelope(
            required_capabilities=[
                {"capability": "read", "justification": ""},  # vazia
            ],
        )


def test_propose_envelope_rejects_oversized_justification() -> None:
    """Justificativa > 200 chars é rejeitada — não é lugar para argumentação."""
    with pytest.raises(ValidationError):
        ProposeEnvelope(
            required_capabilities=[
                {"capability": "read", "justification": "x" * 201},
            ],
        )


def test_propose_envelope_empty_lists_are_valid() -> None:
    """Edge case: tarefa que não requer nada e não exclui nada —
    válido (ainda que estranho). O `EnvelopeMiddleware` filtrará
    tudo por default (deny-all)."""
    proposal = ProposeEnvelope()
    assert proposal.required_capabilities == []
    assert proposal.excluded_capabilities == []
    assert proposal.to_required_set() == set()
    assert proposal.to_excluded_set() == set()


# =========================================================================== #
# B. CapabilityProposal: 1 linha por capability
# =========================================================================== #
def test_capability_proposal_basic() -> None:
    prop = CapabilityProposal(
        capability="write_existing",  # type: ignore[arg-type]
        justification="Refactor de foo.py",
    )
    assert prop.capability == Capability.WRITE_EXISTING
    assert prop.justification == "Refactor de foo.py"


def test_capability_proposal_justification_length_bounds() -> None:
    # min_length=1
    with pytest.raises(ValidationError):
        CapabilityProposal(capability="read", justification="")  # type: ignore[arg-type]

    # max_length=200
    with pytest.raises(ValidationError):
        CapabilityProposal(capability="read", justification="x" * 201)  # type: ignore[arg-type]

    # 1 char (boundary) e 200 chars (boundary) são válidos
    CapabilityProposal(capability="read", justification="x")  # type: ignore[arg-type]
    CapabilityProposal(capability="read", justification="x" * 200)  # type: ignore[arg-type]


# =========================================================================== #
# C. REQ-002: GrantDecision é exclusivo do humano
# =========================================================================== #
def test_grant_decision_basic() -> None:
    d = GrantDecision(granted_capabilities=["read", "write_existing"])
    assert d.to_granted_set() == {Capability.READ, Capability.WRITE_EXISTING}
    assert d.edited is False
    assert d.rejected is False


def test_grant_decision_with_edited_flag() -> None:
    d = GrantDecision(
        granted_capabilities=["read"],  # humano editou
        edited=True,
    )
    assert d.edited is True
    assert d.rejected is False


def test_grant_decision_with_rejected_flag() -> None:
    d = GrantDecision(rejected=True)
    assert d.rejected is True
    # granted_capabilities é ignorado quando rejected=True.
    assert d.to_granted_set() == set()


def test_grant_decision_rejects_unknown_capability() -> None:
    with pytest.raises(ValidationError):
        GrantDecision(granted_capabilities=["not_a_capability"])


# =========================================================================== #
# D. apply_grant_to_middleware: ciclo de aplicação
# =========================================================================== #
def test_apply_grant_sets_envelope() -> None:
    """Caso normal: o grant é aplicado ao middleware."""
    mw = EnvelopeMiddleware()
    decision = GrantDecision(granted_capabilities=["read", "write_existing"])

    applied = apply_grant_to_middleware(decision, mw)

    assert applied == {Capability.READ, Capability.WRITE_EXISTING}
    assert mw.granted == frozenset({Capability.READ, Capability.WRITE_EXISTING})


def test_apply_grant_is_idempotent() -> None:
    """Aplicar o mesmo grant duas vezes dá o mesmo resultado."""
    mw = EnvelopeMiddleware()
    d = GrantDecision(granted_capabilities=["read"])

    apply_grant_to_middleware(d, mw)
    apply_grant_to_middleware(d, mw)

    assert mw.granted == frozenset({Capability.READ})


def test_apply_grant_overwrites_previous_envelope() -> None:
    """Um novo grant SOBRESCREVE o envelope anterior — cada turno
    começa do zero (REQ-002: 'não é herdada por tarefas subsequentes')."""
    mw = EnvelopeMiddleware(granted={Capability.READ})
    decision = GrantDecision(granted_capabilities=["write_existing"])

    apply_grant_to_middleware(decision, mw)

    # O envelope anterior (`read`) foi SUBSTITUÍDO por `write_existing`.
    assert Capability.READ not in mw.granted
    assert Capability.WRITE_EXISTING in mw.granted


def test_apply_rejection_zeros_envelope() -> None:
    """REQ-002 cenário 'ausência de resposta' equivalente:
    rejeição zera o envelope (fail-closed)."""
    mw = EnvelopeMiddleware(granted={Capability.READ, Capability.WRITE_EXISTING})
    decision = GrantDecision(rejected=True)

    applied = apply_grant_to_middleware(decision, mw)

    assert applied == set()
    assert mw.granted == frozenset()


def test_apply_grant_to_frozen_middleware_raises() -> None:
    """Frozen mode protege contra grant acidental."""
    mw = EnvelopeMiddleware(granted={Capability.READ}, frozen=True)
    decision = GrantDecision(granted_capabilities=["write_existing"])

    with pytest.raises(RuntimeError, match="congelado|frozen"):
        apply_grant_to_middleware(decision, mw)


# =========================================================================== #
# E. propose_envelope_tool: interrupt() e grant
# =========================================================================== #
def test_propose_envelope_tool_has_correct_name() -> None:
    """O nome do tool é exposto como constante pública para
    outras camadas (e.g. middleware que precisa interceptá-lo)."""
    assert PROPOSE_ENVELOPE_TOOL_NAME == "propose_envelope"
    # O nome runtime da tool é o canônico (= a constante), para que o
    # plano de controle (`CONTROL_PLANE_TOOLS`) a reconheça e nunca a
    # esconda/bloqueie — do contrário a própria concessão seria impossível.
    assert propose_envelope_tool.name == PROPOSE_ENVELOPE_TOOL_NAME


def _invoke_propose(
    args: dict[str, Any], call_id: str = "tc-1", state: dict[str, Any] | None = None
) -> Any:
    """Invoca `propose_envelope_tool` no formato de ToolCall.

    O `tool_call_id` (InjectedToolCallId) só é populado quando a tool é
    invocada com um dict de ToolCall (`type/id/name/args`), não com um
    dict de args puro. Este helper monta o envelope de ToolCall.

    `state` (InjectedState) também não é auto-injetado fora de um
    `ToolNode` real — em produção (dentro do grafo) o runtime injeta o
    state do grafo; aqui simulamos passando-o como um arg comum. Default
    `{}` = turno sem grant prévio (primeira proposta do turno).
    """
    full_args = {**args, "state": state if state is not None else {}}
    return propose_envelope_tool.invoke(
        {
            "type": "tool_call",
            "id": call_id,
            "name": "propose_envelope_tool",
            "args": full_args,
        }
    )


def _tool_message_content(command: Any) -> str:
    """Extrai o conteúdo da `ToolMessage` de um `Command` devolvido."""
    from langgraph.types import Command

    assert isinstance(command, Command), (
        f"esperado Command, obtido {type(command).__name__}"
    )
    return command.update["messages"][0].content


def test_propose_envelope_tool_writes_grant_to_state() -> None:
    """Quando o tool é invocado, ele chama `interrupt()` (única via de
    concessão, REQ-002) e devolve um `Command` que escreve o envelope
    concedido no STATE do grafo — a fonte da verdade que o
    `EnvelopeMiddleware` lê. Não há atributo de instância mutado.

    NOTA: `interrupt()` real só dispara DENTRO do grafo; aqui mockamos
    para verificar o payload e o `Command` resultante.
    """
    from src.agents.unified import envelope_proposal

    called: list[Any] = []
    original = envelope_proposal.interrupt
    envelope_proposal.interrupt = lambda value: called.append(value) or {  # type: ignore[assignment]
        "granted_capabilities": ["read", "write_existing"],
        "edited": False,
        "rejected": False,
    }
    try:
        command = _invoke_propose(
            {
                "required_capabilities": [
                    {"capability": "read", "justification": "x"},
                ],
                "excluded_capabilities": ["shell"],
            }
        )
    finally:
        envelope_proposal.interrupt = original  # type: ignore[assignment]

    # O `interrupt` foi chamado com o payload correto.
    assert len(called) == 1
    interrupt_value = called[0]
    assert interrupt_value["type"] == "envelope_proposal"
    assert (
        interrupt_value["proposal"]["required_capabilities"][0]["capability"]
        == "read"
    )
    assert interrupt_value["proposal"]["excluded_capabilities"] == ["shell"]

    # O Command escreve o envelope concedido no state (não em instância).
    assert command.update["granted_capabilities"] == ["read", "write_existing"]
    # E devolve a ToolMessage de confirmação, com o tool_call_id injetado.
    msg = command.update["messages"][0]
    assert "CONCEDIDO" in msg.content
    assert msg.tool_call_id == "tc-1"


def test_propose_envelope_tool_validates_input_upfront() -> None:
    """Inputs inválidos viram `ValidationError` antes do `interrupt()` —
    o modelo recebe um erro estruturado, não um tool call que pausa
    indevidamente."""
    with pytest.raises(ValidationError):
        _invoke_propose(
            {
                "required_capabilities": [
                    {"capability": "unknown_cap", "justification": "x"},
                ],
            }
        )


def test_propose_envelope_tool_resumes_with_grant() -> None:
    """O fluxo completo: o tool é chamado, levanta interrupt; o caller
    resume com um `Command(resume=decision)`; o tool devolve um
    `Command` que escreve o grant no state.

    NOTA: simulamos o resume via mock do `interrupt` (a API real de
    resume é via `Command` no grafo, testada em
    `test_envelope_lifecycle.py`).
    """
    from src.agents.unified import envelope_proposal

    class _MockInterrupt:
        def __init__(self) -> None:
            self.called_with: Any = None

        def __call__(self, value: Any) -> Any:
            self.called_with = value
            return {
                "granted_capabilities": ["read", "write_existing"],
                "edited": True,
                "rejected": False,
            }

    mock = _MockInterrupt()
    original = envelope_proposal.interrupt
    envelope_proposal.interrupt = mock  # type: ignore[assignment]
    try:
        command = _invoke_propose(
            {
                "required_capabilities": [
                    {"capability": "read", "justification": "x"},
                    {"capability": "write_existing", "justification": "y"},
                ],
            }
        )
    finally:
        envelope_proposal.interrupt = original  # type: ignore[assignment]

    # O grant foi escrito no state.
    assert command.update["granted_capabilities"] == ["read", "write_existing"]
    content = _tool_message_content(command)
    assert "CONCEDIDO" in content
    assert "editado" in content
    # O `interrupt` foi chamado com o payload da proposta.
    assert mock.called_with["type"] == "envelope_proposal"
    assert len(mock.called_with["proposal"]["required_capabilities"]) == 2


def test_propose_envelope_tool_resumes_with_rejection() -> None:
    """O complemento: o humano rejeita. O tool devolve um `Command` que
    ZERA o envelope no state (fail-closed) e a ToolMessage diz REJEITADO."""
    from src.agents.unified import envelope_proposal

    mock_value = {"granted_capabilities": [], "edited": False, "rejected": True}
    original = envelope_proposal.interrupt
    envelope_proposal.interrupt = lambda _v: mock_value  # type: ignore[assignment]
    try:
        command = _invoke_propose(
            {
                "required_capabilities": [
                    {"capability": "write_existing", "justification": "x"},
                ],
            }
        )
    finally:
        envelope_proposal.interrupt = original  # type: ignore[assignment]

    # Fail-closed: envelope vazio no state (não havia grant prévio no turno).
    assert command.update["granted_capabilities"] == []
    assert "REJEITADO" in _tool_message_content(command)


# =========================================================================== #
# E2. Escalada (REQ-005, task envelope-5): 2ª proposta no mesmo turno
# =========================================================================== #
def test_escalation_grant_unions_with_previously_granted() -> None:
    """Uma 2ª chamada a `propose_envelope_tool` no mesmo turno (o
    mecanismo de escalada — REQ-005: pedir ampliação em vez de falhar
    em silêncio ou contornar) NÃO substitui o envelope já concedido —
    ela SOMA. Sem isto, pedir `vcs` no meio do turno apagaria
    silenciosamente o `write_existing` já concedido e em uso."""
    from src.agents.unified import envelope_proposal

    original = envelope_proposal.interrupt
    envelope_proposal.interrupt = lambda _v: {  # type: ignore[assignment]
        "granted_capabilities": ["vcs"],
        "edited": False,
        "rejected": False,
    }
    try:
        command = _invoke_propose(
            {
                "required_capabilities": [
                    {"capability": "vcs", "justification": "commitar"},
                ],
            },
            call_id="tc-escalate",
            state={"granted_capabilities": ["write_existing"]},
        )
    finally:
        envelope_proposal.interrupt = original  # type: ignore[assignment]

    # write_existing (turno já tinha) + vcs (escalada) — união, não substituição.
    assert command.update["granted_capabilities"] == ["vcs", "write_existing"]
    assert "CONCEDIDO" in _tool_message_content(command)


def test_escalation_rejection_preserves_previously_granted() -> None:
    """Rejeitar uma escalada nega só o INCREMENTO pedido — não revoga
    o que já estava concedido antes nesse turno (diferente de rejeitar
    a PRIMEIRA proposta do turno, em que não há nada prévio a preservar)."""
    from src.agents.unified import envelope_proposal

    original = envelope_proposal.interrupt
    envelope_proposal.interrupt = lambda _v: {  # type: ignore[assignment]
        "granted_capabilities": [],
        "edited": False,
        "rejected": True,
    }
    try:
        command = _invoke_propose(
            {
                "required_capabilities": [
                    {"capability": "shell", "justification": "rodar script"},
                ],
            },
            call_id="tc-escalate-reject",
            state={"granted_capabilities": ["write_existing"]},
        )
    finally:
        envelope_proposal.interrupt = original  # type: ignore[assignment]

    # write_existing sobrevive à rejeição da escalada por `shell`.
    assert command.update["granted_capabilities"] == ["write_existing"]
    assert "REJEITADO" in _tool_message_content(command)


# =========================================================================== #
# E3. Contradição D4 (task envelope-5): reportada ANTES da concessão
# =========================================================================== #
def test_shell_proposal_excluding_write_existing_warns_before_grant() -> None:
    """D4: propor `shell` E excluir explicitamente `write_existing` é a
    contradição textual do design ("shell sim, edit não" mente). O
    aviso deve estar no payload do `interrupt()` — visível ao humano
    ANTES de ele decidir, não só depois."""
    from src.agents.unified import envelope_proposal

    original = envelope_proposal.interrupt
    captured: list[Any] = []
    envelope_proposal.interrupt = lambda value: captured.append(value) or {  # type: ignore[assignment]
        "granted_capabilities": ["shell"],
        "edited": False,
        "rejected": False,
    }
    try:
        _invoke_propose(
            {
                "required_capabilities": [
                    {"capability": "shell", "justification": "rodar script"},
                ],
                "excluded_capabilities": ["write_existing"],
            },
            call_id="tc-contradiction",
        )
    finally:
        envelope_proposal.interrupt = original  # type: ignore[assignment]

    assert len(captured) == 1
    assert "contradiction_warning" in captured[0]
    assert "write_existing" in captured[0]["contradiction_warning"]


def test_shell_proposal_without_exclusion_has_no_warning() -> None:
    """Pedir `shell` sozinho (sem excluir nada que ele engloba) não é
    contraditório — não há aviso no payload."""
    from src.agents.unified.effects import Capability
    from src.agents.unified.envelope_proposal import detect_shell_contradiction

    assert detect_shell_contradiction({Capability.SHELL}, set()) == frozenset()
    assert (
        detect_shell_contradiction({Capability.READ}, {Capability.WRITE_EXISTING})
        == frozenset()
    ), "sem shell requerido, não há o que contradizer"


def test_detect_shell_contradiction_matches_design_semantics() -> None:
    """A contradição é `shell` requerido + algo que ele engloba
    EXPLICITAMENTE excluído — não `shell` + algo concedido junto (essa
    é a semântica, diferente, de `effects.is_contradictory_envelope`,
    que já tem seus próprios testes em `test_effects.py` e não é
    tocada aqui)."""
    from src.agents.unified.effects import Capability
    from src.agents.unified.envelope_proposal import detect_shell_contradiction

    assert detect_shell_contradiction(
        {Capability.SHELL}, {Capability.VCS, Capability.READ}
    ) == frozenset({Capability.VCS})


# =========================================================================== #
# F. Integração proposta + middleware
# =========================================================================== #
def test_propose_grant_apply_middleware_full_flow() -> None:
    """O fluxo completo de `envelope-4`:

    1. Agente propõe envelope.
    2. Humano concede.
    3. `apply_grant_to_middleware` aplica no `EnvelopeMiddleware`.
    4. `EnvelopeMiddleware.granted` reflete o grant.

    Este é o caminho feliz: REQ-001 (proposta) + REQ-002 (grant) +
    REQ-007 (1 envelope por turno, não por tool).
    """
    mw = EnvelopeMiddleware()  # vazio por default

    # 1. Proposta
    proposal = ProposeEnvelope(
        required_capabilities=[
            {"capability": "read", "justification": "Ler"},
            {"capability": "write_existing", "justification": "Refatorar"},
        ],
        excluded_capabilities=["shell", "vcs"],
    )

    # 2. Grant (humano aprova como está — `edited=False`)
    decision = GrantDecision(
        granted_capabilities=sorted(
            [c.value for c in proposal.to_required_set()]
        ),
        edited=False,
    )

    # 3 + 4. Aplicação
    applied = apply_grant_to_middleware(decision, mw)
    assert applied == {Capability.READ, Capability.WRITE_EXISTING}
    assert mw.granted == frozenset({Capability.READ, Capability.WRITE_EXISTING})


def test_human_can_edit_proposal_before_granting() -> None:
    """O humano pode editar — `edited=True` é apenas informativo,
    mas o `granted_capabilities` é o que vale."""
    _proposal = ProposeEnvelope(  # noqa: F841 — proposta original, mantida para legibilidade
        required_capabilities=[
            {"capability": "read", "justification": "x"},
            {"capability": "write_existing", "justification": "y"},
            {"capability": "shell", "justification": "z"},  # humano vai remover
        ],
    )
    # Humano remove `shell` da proposta e marca `edited=True`.
    decision = GrantDecision(
        granted_capabilities=["read", "write_existing"],
        edited=True,
    )
    mw = EnvelopeMiddleware()
    applied = apply_grant_to_middleware(decision, mw)
    assert Capability.SHELL not in applied
    assert decision.edited is True  # informativo


# =========================================================================== #
# G. Tarefas só de leitura não pedem envelope (REQ-001)
# =========================================================================== #
def test_read_only_proposal_is_valid_but_redundant() -> None:
    """Tarefa que usa APENAS Tier 1 (read) pode propor `read`, mas não
    precisa: o bypass é aplicado pelo **código**, não por convenção de prompt.

    `EnvelopeMiddleware._tool_allowed_in_envelope` (`envelope_middleware.py`)
    deixa passar qualquer tool cujas capacidades efetivas estejam inteiramente
    em `FLOOR_CAPABILITIES`, **independente do `granted` set** — inclusive com
    `granted=set()` (o caso de uma tarefa que nunca chamou `propose_envelope`).
    É esse piso, não uma instrução de system prompt, que satisfaz o cenário
    "tarefa apenas de leitura" do REQ-001 ("sem atrito onde não há risco").

    Este teste confirma as duas metades: (a) o schema `ProposeEnvelope`
    aceita uma proposta com apenas `read`, para quando o agente decidir
    propor mesmo assim; e (b) uma tool de piso passa pelo filtro do
    `EnvelopeMiddleware` com envelope vazio, sem precisar de proposta.
    """
    proposal = ProposeEnvelope(
        required_capabilities=[
            {"capability": "read", "justification": "x"},
        ],
    )
    assert Capability.READ in proposal.to_required_set()

    # (b) Bypass de piso: uma tool read-only passa com granted=set() —
    # comportamento do código, não do prompt.
    from src.agents.unified.envelope_middleware import _tool_allowed_in_envelope

    assert _tool_allowed_in_envelope("read_project_file", granted=set())


# =========================================================================== #
# H. Granularidade: o grant é por TURNO, não por tool call (REQ-007)
# =========================================================================== #
def test_grant_does_not_expire_within_single_turn() -> None:
    """REQ-007: 1 grant por turno. Dentro do turno, múltiplas
    tool calls usam o mesmo envelope. Aqui testamos o invariante
    da implementação: `apply_grant_to_middleware` é idempotente
    e não decremental — o envelope permanece até o próximo turno.

    A "expiração entre turnos" será responsabilidade do
    `EnvelopeLifecycleMiddleware` (ainda não implementado nesta
    task — o foco aqui é o ciclo de vida do grant, não as
    fronteiras do turno)."""
    mw = EnvelopeMiddleware()
    d = GrantDecision(granted_capabilities=["read", "write_existing"])

    # Aplica o grant 12 vezes (simulando 12 tool calls no turno).
    for _ in range(12):
        apply_grant_to_middleware(d, mw)

    # O envelope é o mesmo — não expirou entre as 12 chamadas.
    assert mw.granted == frozenset({Capability.READ, Capability.WRITE_EXISTING})


# =========================================================================== #
# I. Schema dump/load round-trip (Pydantic)
# =========================================================================== #
def test_proposal_serialization_round_trip() -> None:
    """O `ProposeEnvelope` é serializável — `interrupt()` precisa
    passar o payload via serialização JSON (via langgraph)."""
    original = ProposeEnvelope(
        required_capabilities=[
            {"capability": "read", "justification": "x"},
        ],
        excluded_capabilities=["shell"],
    )
    # `model_dump` produz um dict; `model_validate` reconstrói.
    dumped = original.model_dump()
    json_str = json.dumps(dumped)  # serializa via JSON
    loaded = ProposeEnvelope.model_validate(json.loads(json_str))

    assert loaded == original


def test_grant_decision_serialization_round_trip() -> None:
    original = GrantDecision(
        granted_capabilities=["read"], edited=True, rejected=False
    )
    dumped = original.model_dump()
    loaded = GrantDecision.model_validate(dumped)
    assert loaded == original


# =========================================================================== #
# J. Auditabilidade (REQ-009, task envelope-5): logger estruturado
# =========================================================================== #
def test_propose_logs_audit_event(caplog: pytest.LogCaptureFixture) -> None:
    """Toda proposta é logada ANTES do `interrupt()` — mesmo se o humano
    nunca responder, o registro de que a proposta aconteceu existe
    (REQ-009: "o que o agente teve permissão de fazer ontem?")."""
    import logging

    from src.agents.unified import envelope_proposal

    original = envelope_proposal.interrupt
    envelope_proposal.interrupt = lambda _v: {  # type: ignore[assignment]
        "granted_capabilities": ["read"],
        "edited": False,
        "rejected": False,
    }
    try:
        with caplog.at_level(logging.INFO, logger="jeff_ai.envelope_audit"):
            _invoke_propose(
                {
                    "required_capabilities": [
                        {"capability": "read", "justification": "x"},
                    ],
                },
                call_id="tc-audit-propose",
            )
    finally:
        envelope_proposal.interrupt = original  # type: ignore[assignment]

    linhas = [
        r.getMessage()
        for r in caplog.records
        if r.name == "jeff_ai.envelope_audit"
    ]
    assert any("event=propose" in m and "tc-audit-propose" in m for m in linhas)
    assert any("event=grant" in m and "tc-audit-propose" in m for m in linhas)


def test_rejection_logs_audit_event(caplog: pytest.LogCaptureFixture) -> None:
    import logging

    from src.agents.unified import envelope_proposal

    original = envelope_proposal.interrupt
    envelope_proposal.interrupt = lambda _v: {  # type: ignore[assignment]
        "granted_capabilities": [],
        "edited": False,
        "rejected": True,
    }
    try:
        with caplog.at_level(logging.INFO, logger="jeff_ai.envelope_audit"):
            _invoke_propose(
                {
                    "required_capabilities": [
                        {"capability": "shell", "justification": "x"},
                    ],
                },
                call_id="tc-audit-reject",
            )
    finally:
        envelope_proposal.interrupt = original  # type: ignore[assignment]

    linhas = [
        r.getMessage()
        for r in caplog.records
        if r.name == "jeff_ai.envelope_audit"
    ]
    assert any("event=rejected" in m and "tc-audit-reject" in m for m in linhas)


def test_block_logs_audit_event(caplog: pytest.LogCaptureFixture) -> None:
    """`EnvelopeMiddleware.wrap_tool_call` loga cada bloqueio no MESMO
    canal (`jeff_ai.envelope_audit`) que propose/grant/reject."""
    import logging

    from langchain.agents.middleware.types import ToolCallRequest
    from langchain_core.messages import ToolCall

    mw = EnvelopeMiddleware(granted=set())

    def _handler(_req: Any) -> Any:
        raise AssertionError("handler não deveria rodar em bloqueio")

    request = ToolCallRequest(
        tool_call=ToolCall(name="edit_file", args={}, id="c-audit-block"),
        tool=None,  # type: ignore[arg-type]
        state={"messages": []},
        runtime=None,  # type: ignore[arg-type]
    )
    with caplog.at_level(logging.INFO, logger="jeff_ai.envelope_audit"):
        mw.wrap_tool_call(request, _handler)

    linhas = [
        r.getMessage()
        for r in caplog.records
        if r.name == "jeff_ai.envelope_audit"
    ]
    assert any(
        "event=block" in m and "c-audit-block" in m and "edit_file" in m
        for m in linhas
    )


# =========================================================================== #
# K. Métrica de fadiga (REQ-007, task envelope-5): compute_approval_rate
# =========================================================================== #
def test_approval_rate_is_zero_with_no_turns() -> None:
    assert compute_approval_rate([]) == 0.0


def test_approval_rate_one_grant_per_turn_is_healthy() -> None:
    events = [
        {"event": "turn_start"},
        {"event": "grant"},
        {"event": "turn_start"},
        {"event": "grant"},
    ]
    assert compute_approval_rate(events) == 1.0


def test_approval_rate_above_one_signals_fatigue() -> None:
    """Uma tarefa que escalou 2x (propose inicial + 2 escaladas = 3
    `grant`s) numa única `turn_start` produz taxa 3.0 — acima de 1,
    o sinal de fadiga que o R1 do design pede para vigiar."""
    events = [
        {"event": "turn_start"},
        {"event": "grant"},
        {"event": "grant"},
        {"event": "grant"},
    ]
    assert compute_approval_rate(events) == 3.0
