"""`EnvelopeMiddleware` — o coração do harness de permissões por tarefa.

Corresponde à Decision D1 do design da `unified-agent-realignment`:
o envelope é um middleware customizado com **DOIS hooks**, não um.

- `wrap_model_call` → `request.override(tools=[...])`: o modelo **só vê**
  as tools cujas capacidades estão no envelope. Reduz contexto, reduz
  erro de roteamento, e — crucialmente — o modelo **não emite** tool
  calls para tools fora do envelope (G1 do design).
- `wrap_tool_call` → bloqueia antes de executar. Se a tool está fora
  do envelope, devolve uma `ToolMessage(status="error")` **sem chamar
  `handler`** — a tool nunca executa e nunca produz efeito colateral
  (G2 do design).

## Por que os DOIS hooks (defesa em profundidade)

Esconder (via `wrap_model_call`) reduz a *probabilidade* da tentativa:
o modelo nem sabe que a tool existe. Bloquear (via `wrap_tool_call`)
elimina a *consequência*: mesmo que o modelo alucine o nome de uma
tool, ou que uma skill/subagente exponha tools que não estavam no
set do envelope, o `wrap_tool_call` ainda bloqueia.

Só esconder **não é segurança**. Só bloquear **não é contexto** — o
modelo continua vendo 35 tools no prompt, pagando o custo de schema
e errando o roteamento. Os dois juntos fecham a janela.

## Envelope é restritivo, não expansivo (REQ-006)

A interseção vale: uma tool executa se está no envelope **e** se
satisfaz a política de tier. O envelope:

- NÃO pode rebaixar o tier de uma tool;
- NÃO pode remover um `interrupt_on` exigido pelo tier;
- NÃO pode liberar uma tool de Tier 4 sem o denylist do Tier 4;
- NÃO é uma via de escape do gate.

O envelope apenas FILTRA o conjunto de tools visíveis/executáveis.
A política de tier continua valendo — incluindo para tools que estão
no envelope.

## Composição com o gate de tiers (REQ-006)

| Envelope | Tier | Resultado                                       |
|----------|------|-------------------------------------------------|
| fora     | *    | bloqueia (G2, não chega ao gate)                |
| dentro   | 1/2  | executa direto                                  |
| dentro   | 3/4  | `interrupt_on` decide (diff preview / denylist) |

## Atribuição por EFEITO, não por NOME de tool (D3)

O envelope é um conjunto de **capacidades** (`Capability` de
`effects.py`), não de nomes de tools. Uma tool com efeito `write_existing`
(o mesmo de `edit_file`) é bloqueada se `write_existing` está fora do
envelope — mesmo que o nome da tool seja diferente. Isto fecha o
cenário `task-scoped-permissions` REQ-005 ("contorno por tool
equivalente") por construção.

## Aditivo (rollback trivial)

Remover o middleware da lista `middleware=[]` de `create_deep_agent`
restaura o comportamento anterior sem tocar em mais nada. Isto está
documentado em `envelope-3` (esta task) e é o que torna a change
**Fase 1** opt-in.
"""
from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any, NotRequired

from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import AgentState, ModelRequest, ToolCallRequest
from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool
from langgraph.types import Command

from src.agents.unified.effects import (
    FLOOR_CAPABILITIES,
    TOOL_EFFECTS,
    Capability,
    classify,
    has_capability,
    is_control_plane,
)

# Mesmo logger estruturado usado por `envelope_proposal.py` — o audit
# trail de propose/grant/reject e de block vivem no mesmo canal
# (REQ-009), espelhando o padrão de `jeff_ai.shell_audit`.
_audit_log = logging.getLogger("jeff_ai.envelope_audit")

# Chave do envelope concedido no state do grafo. É `EnvelopeLifecycleMiddleware`
# (em `envelope_proposal.py`) quem escreve e zera esta chave; aqui só lemos.
GRANTED_STATE_KEY = "granted_capabilities"


class EnvelopeState(AgentState):
    """State do grafo estendido com o envelope concedido para o turno corrente.

    O envelope é **per-thread** (cada conversa tem o seu) e **checkpointado**
    (sobrevive ao `interrupt`/`resume` da concessão humana). A chave é escrita
    pelo `propose_envelope_tool` na concessão e ZERADA pelo `before_agent` do
    `EnvelopeLifecycleMiddleware` no início de cada turno — é assim que a
    concessão expira e não é herdada pela tarefa seguinte (REQ-002).

    `NotRequired`: no primeiro turno, antes de qualquer `before_agent`, a chave
    pode não existir. Os leitores tratam ausência como "envelope vazio" —
    deny-all acima do piso, o caso mais restritivo.
    """

    granted_capabilities: NotRequired[list[str]]


# Mensagem padrão quando uma tool é bloqueada. Inclui o nome da tool
# para que o modelo saiba o que aconteceu e possa pedir ampliação
# explícita ao humano (REQ-005 do `task-scoped-permissions`).
_DEFAULT_BLOCK_MESSAGE = (
    "BLOQUEADO pelo envelope da tarefa: a tool '{tool_name}' exige a "
    "capacidade '{required}', que não foi concedida. Se você precisa "
    "dela, peça ampliação explícita do envelope ao humano."
)


def _tool_name(tool: BaseTool | dict[str, Any]) -> str:
    """Extrai o nome de uma tool, seja ela um `BaseTool` ou um dict.

    `request.tools` no `ModelRequest` é `list[BaseTool | dict[str, Any]]`
    — alguns middlewares (e o `bind_tools` da `ChatOllama`) podem passar
    tools como dicts em vez de objetos. Esta função lida com ambos.
    """
    if isinstance(tool, BaseTool):
        return tool.name
    if isinstance(tool, dict):
        # Caso comum: `{"name": "...", "description": "...", "parameters": {...}}`.
        name = tool.get("name")
        if isinstance(name, str) and name:
            return name
    return ""


def _capability_required(tool_name: str) -> Capability:
    """Devolve a capability mais característica de uma tool para a mensagem de bloqueio.

    Para tools com múltiplas capabilities, pegamos a primeira não-`UNKNOWN`.
    Ferramentas desconhecidas de origem NÃO-MCP caem em `UNKNOWN` — que já é
    Tier 3+ no `tier_config`, então o `wrap_tool_call` não costuma ser
    atingido para elas (HITL pausa antes). Mas a defesa em profundidade
    também existe aqui. Tools MCP desconhecidas caem em `NETWORK`, não
    `UNKNOWN`, desde `remove-mcp-unknown-failsafe`.
    """
    caps = classify(tool_name)
    non_unknown = [c for c in caps if c is not Capability.UNKNOWN]
    if non_unknown:
        return non_unknown[0]
    return Capability.UNKNOWN


# --------------------------------------------------------------------------- #
# EnvelopeMiddleware
# --------------------------------------------------------------------------- #
class EnvelopeMiddleware(AgentMiddleware[Any, Any, Any]):
    """Filtra tools por EFEITO (capability) em ambos os hooks do agent loop.

    A instanciação é simples: passar o conjunto de capabilities
    concedidas na construção. O envelope é mutável — o caller pode
    `envelope.granted.add(...)` entre invocações do agente se o
    fluxo exigir (e.g. depois de um passo "propose envelope").

    Para a v1 da change, a concessão é **explícita** (vinda de um
    humano via `interrupt_on`) e **1× por tarefa**. O middleware não
    tenta adivinhar o envelope — `granted` começa vazio por default,
    o que é o caso mais restritivo.

    Parameters
    ----------
    granted:
        Conjunto inicial de capabilities concedidas. Vazio = deny-all
        (a única tool que sobra é nenhuma). Para um envelope de
        "refactor" típico, seria algo como
        `{Capability.READ, Capability.WRITE_EXISTING, Capability.VCS}`.
    block_message:
        Mensagem devolvida ao modelo quando a tool é bloqueada.
        Default usa o formato padrão com nome da tool e capability
        necessária — útil para o modelo pedir ampliação.
    frozen:
        Se `True`, `granted` não pode ser alterado após a construção.
        Útil em modo "lock-down" para testes e para o caso em que
        o envelope é congelado por um humano após concessão.

    Attributes:
    ----------
    granted:
        `set[Capability]` mutável (a menos que `frozen=True`).
    blocked_calls:
        Lista de `tool_call.id` que foram bloqueadas — útil para
        auditoria (REQ-009 do `task-scoped-permissions`).
    """

    state_schema = EnvelopeState

    def __init__(
        self,
        granted: Iterable[Capability] | None = None,
        *,
        block_message: str | None = None,
        frozen: bool = False,
    ) -> None:
        """Inicializa o middleware com um envelope inicial.

        Ver a docstring da classe para os parâmetros.
        """
        super().__init__()
        self._granted: set[Capability] = set(granted or ())
        self._frozen = frozen
        self._block_template = block_message or _DEFAULT_BLOCK_MESSAGE
        self._lock = threading.Lock()
        # Auditoria: incrementa a cada bloqueio (REQ-009).
        self.blocked_calls: list[str] = []

    # ------------------------------------------------------------------ #
    # Envelope (granted set) — leitura, escrita, congelamento
    # ------------------------------------------------------------------ #
    @property
    def granted(self) -> frozenset[Capability]:
        """Acesso SOMENTE-LEITURA ao conjunto de capabilities concedidas.

        Para modificar, use `set_granted(...)` ou `grant(...)` /
        `deny(...)` — que respeitam o flag `frozen`.

        Devolver um `frozenset` evita que o caller faça
        `envelope.granted.add(...)` por acidente — uma fonte
        conhecida de bugs (o caller pensa estar modificando
        um set mas está modificando o estado interno).
        """
        return frozenset(self._granted)

    def set_granted(self, granted: Iterable[Capability]) -> None:
        """Substitui o envelope por um novo conjunto.

        Lança `RuntimeError` se o envelope está congelado.
        """
        with self._lock:
            if self._frozen:
                raise RuntimeError(
                    "EnvelopeMiddleware está congelado (frozen=True). "
                    "Não é possível alterar o envelope após a construção."
                )
            self._granted = set(granted)

    def grant(self, capability: Capability) -> None:
        """Adiciona uma capability ao envelope."""
        with self._lock:
            if self._frozen:
                raise RuntimeError(
                    "EnvelopeMiddleware está congelado (frozen=True). "
                    "Não é possível conceder capabilities após a construção."
                )
            self._granted.add(capability)

    def deny(self, capability: Capability) -> None:
        """Remove uma capability do envelope."""
        with self._lock:
            if self._frozen:
                raise RuntimeError(
                    "EnvelopeMiddleware está congelado (frozen=True). "
                    "Não é possível negar capabilities após a construção."
                )
            self._granted.discard(capability)

    # ------------------------------------------------------------------ #
    # Hook 1: wrap_model_call — esconde tools fora do envelope
    # ------------------------------------------------------------------ #
    def _resolve_granted(self, state: Any) -> set[Capability]:
        """Resolve o envelope em vigor: o state do grafo tem precedência.

        O grant vive no **state do grafo** (`granted_capabilities`), escrito
        pelo `EnvelopeLifecycleMiddleware` quando o humano concede. É
        per-thread e checkpointado — dois threads não compartilham envelope,
        e a concessão expira quando o `before_agent` do próximo turno zera a
        chave. Ver Q7 do design.

        O atributo de instância `self._granted` é o **fallback** para testes
        unitários que constroem `EnvelopeMiddleware(granted={...})` e chamam
        os hooks diretamente, sem um grafo. Em produção o state manda; se a
        chave existir no state (mesmo que vazia = `[]`), ela vence — um
        envelope vazio concedido é uma decisão, não ausência de dado.
        """
        if isinstance(state, Mapping) and GRANTED_STATE_KEY in state:
            raw = state.get(GRANTED_STATE_KEY) or []
            return {Capability(c) for c in raw}
        return set(self._granted)

    def _filtered_model_request(self, request: ModelRequest) -> ModelRequest:
        """Núcleo compartilhado de `wrap_model_call`/`awrap_model_call`.

        Implementa G1 do design: o modelo **vê** apenas as tools
        cujas capabilities estão no envelope. Reduz contexto,
        reduz erro de roteamento, e — crucialmente — o modelo
        não emite tool calls para tools fora do envelope (a
        única forma de o modelo invocar uma tool é se ela
        estiver no set de tools exposto).

        **Defesa em profundidade:** se uma skill/subagente
        expuser uma tool NÃO catalogada em `TOOL_EFFECTS` e sem
        origem MCP (prefixo `mcp__`) — ex.: gerada via
        `save_generated_tool` — o `classify()` devolve `UNKNOWN`.
        Pelo contrato desta capability (`task-scoped-permissions`
        REQ-008), essa tool SÓ executa se a capability `UNKNOWN`
        estiver no envelope. `UNKNOWN` é uma capability "larga" —
        concedê-la efetivamente diz "rode qualquer tool não
        catalogada dessa origem". O default seguro é NEGAR — a
        menos que o envelope explicitamente conceda `UNKNOWN`, a
        tool não passa do filtro.

        Tools MCP (prefixo `mcp__`) NÃO catalogadas seguem um
        caminho diferente desde `remove-mcp-unknown-failsafe`:
        `classify()` devolve `NETWORK` (piso) por default, não
        `UNKNOWN` — passam no filtro sem exigir concessão de
        envelope. Ver `effects._mcp_manual_override` e a Decision 1
        do design dessa change.
        """
        granted = self._resolve_granted(request.state)
        filtered = _filter_tools_by_envelope(request.tools, granted)
        return request.override(tools=filtered)

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Any],
    ) -> Any:
        """Versão síncrona de G1. Ver `_filtered_model_request`."""
        return handler(self._filtered_model_request(request))

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Any],
    ) -> Any:
        """Versão assíncrona de G1 — **obrigatória em produção**.

        O langchain 1.x NÃO faz bridge automático de `wrap_model_call`
        (sync) para contexto async: `AgentMiddleware.awrap_model_call`
        levanta `NotImplementedError` por padrão a menos que seja
        sobrescrito explicitamente. O `langgraph-api` roda o grafo via
        `astream()`/`ainvoke()` sempre — então sem este método o
        `unified` real quebra em toda chamada de modelo. Descoberto ao
        testar a task `envelope-7` contra o backend rodando de
        verdade (os testes unitários usavam `agent.invoke()` síncrono
        e nunca pegaram isto).
        """
        return await handler(self._filtered_model_request(request))

    # ------------------------------------------------------------------ #
    # Hook 2: wrap_tool_call — bloqueia tools fora do envelope
    # ------------------------------------------------------------------ #
    def _evaluate_tool_call(
        self, request: ToolCallRequest
    ) -> ToolMessage | None:
        """Núcleo compartilhado de `wrap_tool_call`/`awrap_tool_call`.

        Implementa G2 do design: a tool **não executa** se a
        sua capability não está no envelope. Isto vale mesmo
        se:
        - a tool foi emitida pelo modelo apesar de escondida;
        - a tool foi emitida por uma skill que tinha acesso
          a um set próprio;
        - a tool foi emitida por um subagente.

        Em qualquer um desses casos, o envelope intercepta
        antes da execução. A `ToolMessage` retornada tem
        `status="error"` — é o que o `langgraph` espera quando
        uma tool não executa por motivo de gate.

        Returns:
            `None` se a tool está permitida (caller deve chamar
            `handler`); a `ToolMessage` de bloqueio caso contrário
            (caller **NÃO** deve chamar `handler` — chamá-lo
            executaria a tool, exatamente o que REQ-003 do
            `task-scoped-permissions` proíbe).
        """
        tool_name = request.tool_call.get("name", "")
        tool_call_id = request.tool_call.get("id", "")
        granted = self._resolve_granted(request.state)

        # Passa o `tool_call` para a classificação path-aware: `write_file`
        # sobre um arquivo existente é `write_existing` (REQ-005).
        if _tool_allowed_in_envelope(tool_name, granted, request.tool_call):
            return None

        # Bloqueia. Loga na auditoria.
        with self._lock:
            if tool_call_id:
                self.blocked_calls.append(tool_call_id)

        required = _capability_required(tool_name)
        _audit_log.info(
            "envelope_audit event=block tool_call_id=%r tool=%r "
            "required=%r granted=%r",
            tool_call_id,
            tool_name,
            required.value,
            sorted(c.value for c in granted),
        )
        message = self._block_template.format(
            tool_name=tool_name,
            required=required.value,
        )
        return ToolMessage(
            content=message,
            name=tool_name,
            tool_call_id=tool_call_id,
            status="error",
        )

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command[Any]],
    ) -> ToolMessage | Command[Any]:
        """Versão síncrona de G2. Ver `_evaluate_tool_call`."""
        blocked = self._evaluate_tool_call(request)
        if blocked is not None:
            return blocked
        return handler(request)

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Any],
    ) -> ToolMessage | Command[Any]:
        """Versão assíncrona de G2 — **obrigatória em produção**.

        Mesmo motivo de `awrap_model_call`: sem este override,
        `AgentMiddleware.awrap_tool_call` levanta `NotImplementedError`
        assim que o grafo roda via `astream()`/`ainvoke()` — o caso do
        `langgraph-api` em produção, sempre.
        """
        blocked = self._evaluate_tool_call(request)
        if blocked is not None:
            return blocked
        return await handler(request)


# --------------------------------------------------------------------------- #
# Helpers de filtragem
# --------------------------------------------------------------------------- #
def _filter_tools_by_envelope(
    tools: Sequence[BaseTool | dict[str, Any]],
    granted: set[Capability],
) -> list[BaseTool | dict[str, Any]]:
    """Filtra `tools` para só as que estão no envelope.

    Regras:
    - Tool com capability no envelope → MANTÉM.
    - Tool com capability FORA do envelope → REMOVE.
    - Tool desconhecida não-MCP (não está no `TOOL_EFFECTS`, sem
      prefixo `mcp__`) → capability `UNKNOWN`. Permanece no set
      SOMENTE se `UNKNOWN` está no envelope; do contrário, é
      filtrada (REQ-008).
    - Tool MCP desconhecida (prefixo `mcp__`, sem override em
      `mcp_tool_overrides.json`) → capability `NETWORK` (piso),
      desde `remove-mcp-unknown-failsafe`. Permanece no set sempre
      — `NETWORK` está em `FLOOR_CAPABILITIES`, não depende do
      envelope concedido.
    - Tool com NOME vazio (não conseguimos extrair) → REMOVE
      por segurança. Não há como classificar uma tool sem nome.
    """
    if not tools:
        return list(tools) if tools is not None else []

    out: list[BaseTool | dict[str, Any]] = []
    for tool in tools:
        name = _tool_name(tool)
        if not name:
            # Tool sem nome — impossível classificar. Remove.
            continue
        if _tool_allowed_in_envelope(name, granted):
            out.append(tool)
    return out


def _tool_allowed_in_envelope(
    tool_name: str,
    granted: set[Capability],
    tool_call: dict[str, Any] | None = None,
) -> bool:
    """Verdadeiro se a tool pode rodar sob o envelope `granted`.

    A regra tem exatamente três cláusulas:

    1. **Plano de controle** (`propose_envelope`, `write_todos`, `task`) —
       sempre permitido. Estas tools operam o agente, não o mundo. Gatear
       `propose_envelope` tornaria a própria concessão impossível.

    2. **Piso** — a tool passa sem concessão se TODAS as suas capacidades
       efetivas estão no `FLOOR_CAPABILITIES` (leitura, pesquisa, arquivo
       novo). É o "sem atrito onde não há risco" do REQ-001: uma tarefa de
       leitura pura não pede envelope e ainda assim tem tools.

    3. **Concessão** — qualquer outra tool passa se, e somente se, TODAS as
       suas capacidades efetivas estão em `piso ∪ granted`.

    A conjunção ("todas as capacidades") é deliberada e é o que torna o
    envelope fail-safe. A versão anterior usava disjunção ("qualquer
    capacidade"), o que deixava `install_external_skill`
    (`network + write_new`) passar com apenas `network` concedido — meia
    permissão liberava a tool inteira.

    A classificação é **path-aware** (`tool_call` opcional): `write_file`
    sobre um arquivo existente tem efeito `write_existing` e é bloqueado se
    `write_existing` não foi concedido — mesmo `write_file` sendo Tier 2.
    É assim que o REQ-005 ("contorno por tool equivalente") fecha: negar
    `edit_file` e conceder `write_file` não dá ao agente uma segunda porta
    para o mesmo arquivo.
    """
    if not tool_name:
        return False
    if is_control_plane(tool_name):
        return True

    effective = set(classify(tool_name, tool_call))
    allowed = set(FLOOR_CAPABILITIES) | granted
    return effective <= allowed


__all__ = [
    "GRANTED_STATE_KEY",
    "EnvelopeMiddleware",
    "EnvelopeState",
]


# Re-export do `has_capability` e `classify` para conveniência
# (testes e callers).
__all__ += ["has_capability", "classify", "Capability", "TOOL_EFFECTS"]
