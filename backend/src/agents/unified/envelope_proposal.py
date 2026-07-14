"""`ProposeEnvelope` — o ciclo propor → conceder → expirar do envelope.

Cobre a task `unified-agent-realignment-task-envelope-4` (REQ-001,
REQ-002, REQ-007 do `task-scoped-permissions`). O princípio inegociável:

> Quem escreve as regras não pode ser o agente.

O agente **propõe** um envelope estruturado. O humano **concede**
(ou edita) — o agente não pode se autoconceder. A concessão vale
**uma tarefa** (= um turno do agente, ver Q7 do design) e expira
quando o turno termina.

## Granularidade da tarefa (Q7 do design)

**Uma tarefa = um turno do agente**: do `HumanMessage` que iniciou
o turno até o `AIMessage` final (sem tool calls). Esta é a definição
que minimiza o risco R1 (fadiga de aprovação) e satisfaz REQ-007
(1 concessão por tarefa, não por tool call).

## Componentes

1. **`ProposeEnvelope`** — o schema estruturado que o agente emite.
   Não é texto livre: é um objeto validável, com campos
   `required_capabilities` (lista de capabilities + justificativa)
   e `excluded_capabilities` (lista de capabilities de risco
   que NÃO são pedidas).

2. **`propose_envelope_tool`** — a `StructuredTool` que o agente
   chama para propor. Quando o tool é invocado, o sistema
   pausa via `interrupt()` e o humano responde com um grant.

3. **`GrantDecision`** — o objeto que o humano devolve:
   `{granted_capabilities: list[str], edited: bool}`. `edited=True`
   indica que o humano alterou a proposta antes de conceder.

4. **`apply_grant_to_middleware(grant, middleware)`** — aplica o
   grant à instância de `EnvelopeMiddleware` (de
   `envelope_middleware.py`). Idempotente.

5. **`EnvelopeLifecycleMiddleware`** — middleware de ciclo de
   vida que detecta as bordas do turno (início: novo `HumanMessage`
   ⇒ reset; fim: `AIMessage` sem tool calls ⇒ envelope
   expira no PRÓXIMO turno) e intercepta o
   `propose_envelope_tool` para fazer o interrupt + grant.

## Concessão exclusiva humana (REQ-002)

A função `interrupt()` do langgraph é a única via de concessão.
O `EnvelopeLifecycleMiddleware` chama `interrupt(value=proposal)`
e o resultado de `Command(resume=...)` deve ser um `GrantDecision`.
Autoaprovação, inferência ou timeout NÃO existem: se o humano
não responder, o grafo fica pausado para sempre.

## Aditividade

Este módulo **não** substitui o `EnvelopeMiddleware` — ele é uma
camada de cima que o opera. O `EnvelopeMiddleware` continua
sendo o gate. A composição é:

```
EnvelopeLifecycleMiddleware  → opera o  → EnvelopeMiddleware
(turnos + propose/grant)        estado    (filtragem)
```

Ambos são `AgentMiddleware` e podem ser passados juntos em
`middleware=[EnvelopeLifecycleMiddleware(...), EnvelopeMiddleware()]`
para `create_deep_agent`.

## Auditoria e fadiga (REQ-009 / REQ-007, task `envelope-5`)

Todo `propose`, `grant`/`escalation` e `rejected` é logado no logger
`jeff_ai.envelope_audit` — mesmo padrão do `jeff_ai.shell_audit` já
usado para `run_shell_command` em `src/tools/self_extension.py`. Não
existe (nem esta task inventa) uma tabela de auditoria dedicada; a
consultabilidade (REQ-009: "o que o agente teve permissão de fazer
ontem?") vem de onde já vem para o shell: agregação de log,
fora deste código. `EnvelopeMiddleware.wrap_tool_call` loga cada
bloqueio pelo mesmo logger.

`compute_approval_rate` é a métrica de fadiga (REQ-007) — uma função
pura sobre registros já estruturados (a mesma forma que os logs
emitem), não um dashboard. "Medida" é isto: dado um conjunto de
eventos, a taxa é computável e testável. "Exposta" depende de quem
agrega os logs em produção — não deste módulo.
"""
from __future__ import annotations

import logging
from typing import Annotated, Any, Literal

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from langgraph.runtime import Runtime
from langgraph.types import Command, interrupt
from pydantic import BaseModel, Field

from src.agents.unified.effects import CAPABILITY_NAMES, SHELL_ENCOMPASSES, Capability
from src.agents.unified.envelope_middleware import (
    GRANTED_STATE_KEY,
    EnvelopeMiddleware,
    EnvelopeState,
)

# Mesmo padrão de `src/tools/self_extension.py:31` (`jeff_ai.shell_audit`).
_audit_log = logging.getLogger("jeff_ai.envelope_audit")

# --------------------------------------------------------------------------- #
# Schema da proposta
# --------------------------------------------------------------------------- #
# O Pydantic v2 baseia-se em `pydantic.BaseModel`. Usamos `model_config`
# para extrair config por strict para a v1 — a proposta é um objeto
# estruturado, e campos faltantes não devem ser tolerados.


class CapabilityProposal(BaseModel):
    """Uma capability proposta pelo agente, com justificativa.

    A justificativa é **1 linha** por capacidade (REQ-001 do
    `task-scoped-permissions`). O sistema SHALL rejeitar
    justificativas vazias ou > 200 caracteres — não é lugar
    para argumentação, é para o humano decidir.
    """

    capability: Literal[*CAPABILITY_NAMES]  # type: ignore[valid-type]
    """A capability pedida. Limitada aos valores do enum `Capability`
    (e `UNKNOWN`, que o agente pode pedir para ferramentas MCP
    de terceiro)."""

    justification: str = Field(..., min_length=1, max_length=200)
    """Justificativa de 1 linha (até 200 chars)."""


class ProposeEnvelope(BaseModel):
    """Proposta estruturada de envelope pelo agente.

    REQ-001 do `task-scoped-permissions`: o agente SHALL propor um
    envelope **estruturado** (não texto livre) com:
    - `required_capabilities`: a lista de capabilities que a tarefa
      requer, cada uma com justificativa de 1 linha;
    - `excluded_capabilities`: capabilities de risco (Tier 3/4) que
      a tarefa explicitamente **NÃO** requer — declaração
      obrigatória para o humano saber o que o agente está
      descartando.

    O objeto é validado por Pydantic — campos faltantes ou tipos
    errados são rejeitados antes mesmo de chegar ao humano.
    """

    required_capabilities: list[CapabilityProposal] = Field(
        default_factory=list,
        description=(
            "Capabilities que a tarefa requer, cada uma com "
            "justificativa de 1 linha."
        ),
    )
    excluded_capabilities: list[Literal[*CAPABILITY_NAMES]] = Field(  # type: ignore[valid-type]
        default_factory=list,
        description=(
            "Capabilities de risco (Tier 3/4) que a tarefa "
            "explicitamente NÃO requer."
        ),
    )

    def to_required_set(self) -> set[Capability]:
        """Devolve o conjunto de capabilities requeridas como `Capability`."""
        return {Capability(prop.capability) for prop in self.required_capabilities}

    def to_excluded_set(self) -> set[Capability]:
        """Devolve o conjunto de capabilities excluídas como `Capability`."""
        return {Capability(c) for c in self.excluded_capabilities}


def detect_shell_contradiction(
    required: set[Capability], excluded: set[Capability]
) -> frozenset[Capability]:
    """D4: `shell` requerido e algo que ele engloba explicitamente EXCLUÍDO.

    Esta é a contradição que o design descreve textualmente: "um envelope
    que diz 'pode shell, não pode editar' mente" — porque `shell` já
    concede `write_existing`/`vcs`/`network` na prática (`sed -i`,
    `git commit`, `curl`). A checagem opera sobre a proposta ESTRUTURADA
    do agente (`required_capabilities` + `excluded_capabilities`), não
    sobre o `granted` final — só a proposta tem a lista do que foi
    explicitamente negado, e o objetivo é reportar a contradição ao
    humano ANTES da concessão (`task-scoped-permissions`, task
    `envelope-5`).

    Devolve o subconjunto de `SHELL_ENCOMPASSES` que está simultaneamente
    em `excluded` — vazio significa "sem contradição". Se `shell` não
    está em `required`, é sempre vazio (não há o que contradizer).

    Nota: `effects.is_contradictory_envelope(granted)` é uma função
    diferente, pré-existente, que opera sobre o `granted` final e
    tem semântica própria (já testada em `test_effects.py`) — não é
    usada aqui.
    """
    if Capability.SHELL not in required:
        return frozenset()
    return frozenset(excluded & SHELL_ENCOMPASSES)


def _contradiction_warning(contradiction: frozenset[Capability]) -> str:
    """Monta a mensagem de aviso mostrada ao humano antes da concessão."""
    names = ", ".join(sorted(c.value for c in contradiction))
    return (
        f"CONTRADIÇÃO: a proposta pede 'shell' e ao mesmo tempo exclui "
        f"explicitamente {names}. Conceder 'shell' concede, na prática, "
        f"esses efeitos também (sed -i edita, git commit versiona, curl "
        f"acessa rede) — um envelope não pode permitir shell e negar "
        f"edição/git/rede ao mesmo tempo sem mentir sobre o que está "
        f"contido."
    )


# --------------------------------------------------------------------------- #
# Decisão humana
# --------------------------------------------------------------------------- #
class GrantDecision(BaseModel):
    """A resposta do humano à proposta de envelope.

    REQ-002: a concessão é **exclusivamente humana**. O
    `GrantDecision` é construído pelo caller (em geral, o frontend
    ou o test harness) a partir da interação com o humano, e
    passado de volta via `Command(resume=...)`.

    Attributes:
    ----------
    granted_capabilities:
        O conjunto FINAL de capabilities concedidas. Pode ser
        igual à proposta (edição=False) ou diferente
        (edição=True) — o humano pode editar antes de conceder.
    edited:
        `True` se o humano editou a proposta. Apenas
        informativo; não muda a semântica.
    rejected:
        `True` se o humano rejeitou a proposta. Quando
        `rejected=True`, `granted_capabilities` é ignorado e o
        envelope fica VAZIO para o turno.
    """

    granted_capabilities: list[Literal[*CAPABILITY_NAMES]] = Field(  # type: ignore[valid-type]
        default_factory=list,
        description=(
            "O conjunto final de capabilities concedidas. Ignorado "
            "se `rejected=True`."
        ),
    )
    edited: bool = Field(
        default=False,
        description="True se o humano editou a proposta antes de conceder.",
    )
    rejected: bool = Field(
        default=False,
        description=(
            "True se o humano rejeitou a proposta. O envelope "
            "fica vazio para o turno."
        ),
    )

    def to_granted_set(self) -> set[Capability]:
        """Devolve o conjunto de capabilities concedidas como `Capability`."""
        return {Capability(c) for c in self.granted_capabilities}


# --------------------------------------------------------------------------- #
# Tool: propose_envelope
# --------------------------------------------------------------------------- #
PROPOSE_ENVELOPE_TOOL_NAME = "propose_envelope"


@tool(PROPOSE_ENVELOPE_TOOL_NAME)
def propose_envelope_tool(
    required_capabilities: list[dict[str, str]],
    tool_call_id: Annotated[str, InjectedToolCallId],
    state: Annotated[dict[str, Any], InjectedState],
    excluded_capabilities: list[str] | None = None,
) -> Command:
    """Propor um envelope de permissões para a tarefa atual.

    O agente chama esta tool ANTES de qualquer tool de Tier 3+ ou
    Tier 4. A proposta fica em pausa até o humano responder. Pode ser
    chamada MAIS DE UMA VEZ no mesmo turno — é assim que a **escalada**
    (`task-scoped-permissions` REQ-005) funciona: se uma tool de risco
    surgir no meio da tarefa e não estiver no envelope já concedido, o
    agente chama esta tool de novo pedindo a capability faltante, em
    vez de falhar em silêncio ou tentar um caminho alternativo.

    Args:
        required_capabilities: Lista de `{capability, justification}`
            (uma por capability que a tarefa requer). A justificativa
            tem 1 linha (até 200 chars).
        tool_call_id: Injetado pelo runtime — usado para construir a
            `ToolMessage` de resposta. O modelo NÃO fornece isto.
        state: Injetado pelo runtime (`InjectedState`) — usado para ler
            o envelope JÁ concedido neste turno (ver "Escalada" abaixo).
            O modelo NÃO fornece isto.
        excluded_capabilities: Lista de capabilities de risco
            (Tier 3/4) que a tarefa explicitamente NÃO requer.

    Escalada (REQ-005):
        O novo grant é a UNIÃO do que já estava concedido neste turno
        (lido de `state[GRANTED_STATE_KEY]`) com a decisão humana desta
        chamada — não uma substituição. Sem isso, pedir uma capability
        a mais no meio do turno apagaria silenciosamente o que já havia
        sido concedido (e possivelmente já estava em uso). Uma
        REJEIÇÃO de escalada, pelo mesmo motivo, preserva o que já
        estava concedido — só nega o INCREMENTO pedido, não revoga o
        que veio antes. (Na primeira proposta do turno o "já concedido"
        está vazio, então a fórmula se reduz ao comportamento original.)

    Contradição D4:
        Se a proposta pede `shell` e simultaneamente exclui
        explicitamente algo que `shell` engloba (`write_existing`,
        `vcs`, `network`), um aviso é incluído no payload do
        `interrupt()` — o humano vê a contradição ANTES de decidir
        (`detect_shell_contradiction`).

    Returns:
        Um `Command` que (a) escreve o envelope concedido em
        `state["granted_capabilities"]` — a fonte da verdade que o
        `EnvelopeMiddleware` lê — e (b) devolve uma `ToolMessage` ao
        modelo com o resultado da concessão. Escrever no STATE (e não
        num atributo de instância) é o que torna a concessão
        per-thread, checkpointada e sujeita à expiração por turno.
    """
    # Validação upfront (Pydantic) — campos faltantes / tipos
    # errados viram `ValidationError` que o modelo recebe como
    # `ToolMessage(status="error")`.
    proposal = ProposeEnvelope(
        required_capabilities=[
            CapabilityProposal(**item) for item in required_capabilities
        ],
        excluded_capabilities=list(excluded_capabilities or []),
    )

    previously_granted = {
        Capability(c) for c in (state.get(GRANTED_STATE_KEY) or [])
    }

    interrupt_payload: dict[str, Any] = {
        "type": "envelope_proposal",
        "proposal": proposal.model_dump(),
    }
    contradiction = detect_shell_contradiction(
        proposal.to_required_set(), proposal.to_excluded_set()
    )
    if contradiction:
        interrupt_payload["contradiction_warning"] = _contradiction_warning(
            contradiction
        )

    # Auditoria (REQ-009): registra a PROPOSTA antes do interrupt, para
    # que o registro exista mesmo que o grafo fique pausado indefinidamente
    # sem resposta humana (REQ-002).
    _audit_log.info(
        "envelope_audit event=propose tool_call_id=%r required=%r "
        "excluded=%r previously_granted=%r contradiction=%r",
        tool_call_id,
        sorted(c.value for c in proposal.to_required_set()),
        sorted(c.value for c in proposal.to_excluded_set()),
        sorted(c.value for c in previously_granted),
        sorted(c.value for c in contradiction),
    )

    # Pausa e pede concessão humana. `interrupt()` é a única via
    # (REQ-002). O valor retornado pelo `Command(resume=...)` é
    # devolvido aqui. Sem resposta, o grafo fica pausado para sempre —
    # nada de Tier 3+ executa.
    decision_raw: Any = interrupt(interrupt_payload)

    # Validação da decisão humana. Fail-closed: qualquer coisa que não
    # seja um grant válido preserva o que já estava concedido (não
    # concede nada A MAIS) e nunca REVOGA o que veio antes nesta
    # chamada — ver "Escalada" na docstring.
    if not isinstance(decision_raw, dict):
        _audit_log.info(
            "envelope_audit event=block_invalid_decision tool_call_id=%r",
            tool_call_id,
        )
        return _grant_command(
            sorted(c.value for c in previously_granted),
            tool_call_id,
            "REJEITADO: decisão inválida do humano.",
        )
    decision = GrantDecision.model_validate(decision_raw)

    if decision.rejected:
        _audit_log.info(
            "envelope_audit event=rejected tool_call_id=%r "
            "preserved=%r",
            tool_call_id,
            sorted(c.value for c in previously_granted),
        )
        return _grant_command(
            sorted(c.value for c in previously_granted),
            tool_call_id,
            "REJEITADO: humano rejeitou a proposta. Nenhuma capability "
            "NOVA foi concedida (o que já estava concedido neste turno "
            "permanece).",
        )

    granted_set = previously_granted | decision.to_granted_set()
    granted = sorted(c.value for c in granted_set)
    granted_strs = ", ".join(granted) or "(nenhuma)"
    edited_marker = " (editado)" if decision.edited else ""
    _audit_log.info(
        "envelope_audit event=grant tool_call_id=%r granted=%r edited=%s "
        "escalation=%s",
        tool_call_id,
        granted,
        decision.edited,
        bool(previously_granted),
    )
    return _grant_command(
        granted, tool_call_id, f"CONCEDIDO{edited_marker}: {granted_strs}"
    )


def _grant_command(
    granted: list[str],
    tool_call_id: str,
    content: str,
) -> Command:
    """Monta o `Command` que aplica o grant ao state e responde ao modelo.

    Escreve `granted_capabilities` no state (fonte da verdade lida pelo
    `EnvelopeMiddleware`) e anexa a `ToolMessage` obrigatória — todo
    tool call precisa de uma `ToolMessage` correspondente no histórico,
    senão o langgraph levanta erro na retomada.
    """
    return Command(
        update={
            GRANTED_STATE_KEY: granted,
            "messages": [
                ToolMessage(content=content, tool_call_id=tool_call_id)
            ],
        }
    )


# --------------------------------------------------------------------------- #
# Aplicação do grant ao EnvelopeMiddleware
# --------------------------------------------------------------------------- #
def apply_grant_to_middleware(
    decision: GrantDecision,
    middleware: EnvelopeMiddleware,
) -> set[Capability]:
    """Aplica o `GrantDecision` ao `EnvelopeMiddleware` e devolve o set aplicado.

    A aplicação é **idempotente** e **sobrescreve** qualquer
    envelope anterior. Isto é deliberado: cada turno começa
    com envelope vazio e só adquire capabilities via grant.

    Caso `decision.rejected=True`, o envelope é zerado (fail-closed).

    O `EnvelopeMiddleware.granted` é atualizado em sincronia com
    o `decision.granted_capabilities`. Se o `EnvelopeMiddleware`
    está em `frozen=True`, lança `RuntimeError` (segurança contra
    grant acidental que alteraria um envelope já congelado).
    """
    if decision.rejected:
        new_set: set[Capability] = set()
    else:
        new_set = decision.to_granted_set()

    # `set_granted` respeita `frozen` — se o envelope está
    # congelado, lança. Isto é o caminho seguro.
    middleware.set_granted(new_set)
    return new_set


# --------------------------------------------------------------------------- #
# EnvelopeLifecycleMiddleware — bordas do turno (propor → conceder → EXPIRAR)
# --------------------------------------------------------------------------- #
class EnvelopeLifecycleMiddleware(AgentMiddleware):
    """Zera o envelope no início de cada turno — é aqui que a concessão EXPIRA.

    Q7 do design: **uma tarefa = um turno do agente** (do `HumanMessage`
    inicial ao `AIMessage` final sem tool calls). O `before_agent` roda
    **uma vez por turno** — e NÃO na retomada de um `interrupt` (verificado
    empiricamente: a concessão sobrevive ao `interrupt`/`resume` da própria
    proposta, mas é zerada quando o próximo `HumanMessage` inicia um turno
    novo). Isto satisfaz, por construção:

    - **REQ-002** ("a concessão expira ao fim da tarefa e não é herdada pela
      tarefa seguinte na mesma thread"): o turno seguinte começa com
      `granted_capabilities = []`, então a tarefa B propõe o próprio
      envelope — a concessão de A não vale para B.
    - **REQ-007** ("1 concessão por tarefa, não por tool call"): o
      `before_agent` não roda entre tool calls do mesmo turno, então o
      envelope concedido vale para todas as tool calls daquele turno — uma
      tarefa que edita 12 arquivos foi aprovada UMA vez.

    Este middleware é o **operador** do envelope; o `EnvelopeMiddleware` é o
    **gate**. Os dois são passados juntos em `middleware=[...]` para
    `create_deep_agent`. Ambos declaram o mesmo `state_schema`
    (`EnvelopeState`), de modo que a chave `granted_capabilities` existe no
    state combinado do grafo.

    ⚠️ Ordem: este middleware deve vir ANTES do `EnvelopeMiddleware` na lista
    (ou depois — o `before_agent` roda antes de qualquer `wrap_model_call`,
    então a ordem relativa entre os dois não afeta a expiração). O que
    importa é que AMBOS estejam presentes.
    """

    state_schema = EnvelopeState

    def before_agent(
        self,
        state: Any,
        runtime: Runtime[Any],
    ) -> dict[str, Any] | None:
        """Zera o envelope no início do turno. Ver docstring da classe.

        Retornar `{granted_capabilities: []}` sobrescreve o envelope do
        turno anterior. É a única linha que faz a concessão expirar — sem
        ela, o grant de um turno vazaria para o próximo, violando REQ-002.
        """
        # Auditoria/fadiga (REQ-009/REQ-007): cada turno novo é um
        # `turn_start` — o denominador de `compute_approval_rate`.
        _audit_log.info("envelope_audit event=turn_start")
        return {GRANTED_STATE_KEY: []}


# --------------------------------------------------------------------------- #
# Métrica de fadiga (REQ-007) — função pura sobre registros de auditoria
# --------------------------------------------------------------------------- #
def compute_approval_rate(events: list[dict[str, Any]]) -> float:
    """Taxa de aprovações por tarefa (REQ-007): `grant` / `turn_start`.

    `events` tem a mesma forma dos registros emitidos por `_audit_log`
    (`{"event": "turn_start"}` de `EnvelopeLifecycleMiddleware.before_agent`,
    `{"event": "grant"}` de cada decisão humana resolvida em
    `propose_envelope_tool` — concessão OU escalada, ambas contam como
    uma interação de aprovação).

    Devolve `0.0` se não houver turnos — ausência de dado não é o
    mesmo que fadiga zero, mas também não é "muito acima de 1"; o
    caller decide o que fazer com uma amostra vazia.

    **Racional (risco R1 do design):** uma média MUITO acima de 1 é
    uma falha de SEGURANÇA (o usuário passa a aprovar tudo no
    automático), não uma falha de UX, e SHALL disparar redesenho da
    granularidade do envelope — não é só uma métrica de vaidade.

    Esta função é o que "medida" significa neste código: dado um
    conjunto de eventos (de onde quer que venham — os logs
    `jeff_ai.envelope_audit`, uma agregação de produção, um teste), a
    taxa é computável. "Exposta" (dashboard, alerta) é responsabilidade
    de quem consome os logs — este módulo não afirma ter um.
    """
    turns = sum(1 for e in events if e.get("event") == "turn_start")
    grants = sum(1 for e in events if e.get("event") == "grant")
    if turns == 0:
        return 0.0
    return grants / turns


# --------------------------------------------------------------------------- #
# Exceções
# --------------------------------------------------------------------------- #
class EnvelopeNotGrantedError(RuntimeError):
    """Levantada quando uma tool de Tier 3+ é chamada antes de grant.

    Defesa em profundidade: o `EnvelopeMiddleware.wrap_tool_call`
    já bloqueia tools fora do envelope. Esta exceção é uma
    camada extra, para o caso em que o `EnvelopeMiddleware` foi
    configurado incorretamente (envelope vazio, mas o caller
    espera que a tool rode).
    """


# --------------------------------------------------------------------------- #
# API pública
# --------------------------------------------------------------------------- #
__all__ = [
    "PROPOSE_ENVELOPE_TOOL_NAME",
    "CapabilityProposal",
    "EnvelopeLifecycleMiddleware",
    "EnvelopeNotGrantedError",
    "GrantDecision",
    "ProposeEnvelope",
    "apply_grant_to_middleware",
    "compute_approval_rate",
    "detect_shell_contradiction",
    "propose_envelope_tool",
]


# Re-exports para conveniência.
__all__ += ["Capability"]
