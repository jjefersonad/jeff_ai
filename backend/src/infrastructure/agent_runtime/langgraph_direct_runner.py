"""Adapter LangGraph para `AgentRunnerPort`.

Usa `build_unified` (mesma fábrica da plataforma) contra
`AsyncPostgresSaver` + `AsyncPostgresStore` apontando para `POSTGRES_URI`.

Razão de existir (task `agendamento-jeff-cli-task-runtime-1`):

- `jeff_cli.py` (subprocesso one-shot disparado pelo APScheduler) precisa
  rodar o agente sem depender do processo HTTP do LangGraph estar de pé.
  Compilar `unified` lá dentro via `build_unified(checkpointer=, store=)`
  é a única forma de manter a definição do grafo idêntica à da plataforma
  (decisão `agendamento-jeff-cli-design`: "Invocação direta do grafo").
- O `telegram_gateway.py` (change `integracao-telegram`) reusa o mesmo
  port — não duplica a fábrica do grafo.

Pontos deliberados:
- `AsyncPostgresSaver` e `AsyncPostgresStore` são abertos/fechados POR
  invocação. As tabelas são criadas pelo processo principal (plataforma
  LangGraph ou `langgraph dev`); o runner **não chama `.setup()`** —
  reproduzir a chamada levantaria `ProgrammingError("table already exists")`
  em produção e seria desperdício de I/O em todo run.
- `from_conn_string(...)` é usado (não `from_conn_string_async`): o
  módulo `langgraph.checkpoint.postgres.aio` expõe o construtor
  assíncrono; `AsyncPostgresSaver` é um async context manager —
  `async with` cuida do `aclose()` no fim.
- O `unified_model` é referenciado dentro de `build_unified`. Se o LLM
  primário (Ollama Cloud) e o fallback (OpenRouter) estiverem
  inacessíveis, o `FallbackChatModel` engole a exceção e cai pro
  fallback — o `AgentRunResult` retornado aqui é `"ok"`. Erros que
  vazam (rede totalmente fora, OOM, etc.) viram `status="error"` com a
  mensagem em `error`, nunca exceção propagada (o `RunScheduledTask`
  depende desse contrato para distinguir sucesso de falha).
- Detecção de `__interrupt__` (change `telegram-tool-approval`): quando
  `graph.ainvoke(...)` devolve um estado com a chave `__interrupt__`
  populada (lista não-vazia de `Interrupt` cujo `.value` é o
  `HITLRequest`), o adapter devolve
  `AgentRunResult(status="interrupted", interrupt=InterruptInfo(...))`
  em vez de `status="ok"`. Isso permite que o `telegram_gateway`
  apresente a aprovação via teclado inline (REQ-001 do
  `telegram-tool-approval-spec`). A serialização para `dict` é
  deliberadamente defensiva: o `HITLRequest` real do LangChain tem
  `action_requests`/`review_configs` como tuplas de dataclasses; usamos
  duck-typing via `getattr` (dict OU objeto) para não acoplar este
  adapter ao shape exato do upstream.
- Monkey-patch do bug upstream `langgraph-checkpoint-postgres>=3.0.2`
  (change `fix-langgraph-postgres-uuid-union-bug`): aplicado uma vez
  no boot via `install_postgres_uuid_patch()` (ver
  `_langgraph_postgres_uuid_patch.py`). Sem este patch, qualquer
  `ainvoke()` em uma thread com checkpoint existente falha com
  `psycopg.errors.DatatypeMismatch: UNION types uuid and text cannot
  be matched` em `langgraph.checkpoint.postgres.aio.aget_delta_channel_history`.
- `resume(...)` (change `telegram-tool-approval`): resume um grafo
  pausado em um gate `interrupt_on` com as decisões humanas. Chama
  `graph.ainvoke(Command(resume={"decisions": list(decisions)}), config)`
  e reusa o mesmo `_extract_interrupt` para traduzir o resultado, de
  forma que um segundo interrupt (ex.: um loop de approve/reject
  encadeado) apareça novamente como `status="interrupted"` no DTO.
"""
from __future__ import annotations

import dataclasses
import logging
from typing import Any

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.store.postgres.aio import AsyncPostgresStore
from langgraph.types import Command

from src.agents.unified.agent import build_unified
from src.application.ports.agent_runner import (
    AgentRunnerPort,
    AgentRunResult,
    InterruptInfo,
)
from src.domain.scheduling import ToolScope
from src.infrastructure.agent_runtime._langgraph_postgres_uuid_patch import (
    install_postgres_uuid_patch,
)
from src.infrastructure.usage.user_key import resolve_user_key

# Aplica o monkey-patch do bug upstream `langgraph-checkpoint-postgres>=3.0.2`
# (`UNION types uuid and text cannot be matched` em
# `_build_delta_stage2_sql`). Roda uma única vez no boot, antes de
# qualquer uso de `AsyncPostgresSaver`/`AsyncPostgresStore`. Idempotente
# (ver `install_postgres_uuid_patch`). See
# `fix-langgraph-postgres-uuid-union-bug-design` para contexto completo.
install_postgres_uuid_patch()

logger = logging.getLogger(__name__)


def _build_run_config(
    *,
    thread_id: str,
    user_key: str | None,
) -> dict[str, Any]:
    """Monta a config LangGraph com identidade do run.

    `configurable` carrega `thread_id` e `user_key` (resolvido via
    `resolve_user_key` — sentinel `unknown` se ausente). O
    `UsageRecordingCallback` vive no grafo (`build_unified` /
    `_unified_run_config`) — não aqui — para cobrir web + DirectRunner
    sem double-record (track-user-token-usage recording-5).
    """
    resolved = resolve_user_key(user_key=user_key)
    return {
        "configurable": {
            "thread_id": thread_id,
            "user_key": resolved,
        },
    }


def _extract_interrupt(state: Any) -> InterruptInfo | None:  # noqa: ANN401
    """Extrai `InterruptInfo` do estado retornado por `ainvoke`, se houver.

    Devolve `None` se não houver pause (sem `__interrupt__` ou lista vazia,
    ou `state` não-dict — defesa em profundidade contra `ainvoke` devolver
    algo exótico). Caso haja pause, serializa `action_requests` e
    `review_configs` do PRIMEIRO `Interrupt.value` para `tuple[dict, ...]`
    — o design (`telegram-tool-approval-design` Decision #1) fixa
    "1 `HITLRequest` por interrupt" para o caso real
    (`image_design_subagent`); o `telegram_gateway` consome
    `InterruptInfo` e renderiza a UI.

    Duck-typed: `value` pode ser um dict (caso simples) ou um
    `HITLRequest` do LangChain (dataclass). A serialização
    `dataclasses.asdict` cobre o segundo caso; o primeiro passa direto
    porque iterar/tuplicar um dict-like já produz tuplas de dicts.

    A chave `__interrupt__` segue a convenção do LangGraph: tuple de
    `Interrupt`. Lista vazia é tratada como "sem pause" — o grafo
    pode emitir `__interrupt__: ()` em estados de "ainda em execução"
    ou "limpo", e isso NÃO deve virar `status="interrupted"`.
    """
    if not isinstance(state, dict):
        return None
    raw = state.get("__interrupt__")
    if not raw:
        return None
    try:
        first = raw[0]
    except (TypeError, IndexError):
        return None
    value = getattr(first, "value", first)
    if value is None:
        return None

    # Extrai `action_requests` e `review_configs` do `value`, duck-typed.
    if isinstance(value, dict):
        action_requests = value.get("action_requests", ())
        review_configs = value.get("review_configs", ())
    else:
        action_requests = getattr(value, "action_requests", ())
        review_configs = getattr(value, "review_configs", ())

    def _serialize(item: Any) -> dict[str, Any]:  # noqa: ANN401
        if dataclasses.is_dataclass(item):
            return dataclasses.asdict(item)
        if isinstance(item, dict):
            return dict(item)
        # Fallback: melhor serializar em dict vazio do que explodir — o
        # `telegram_gateway` precisa de algo iterável; um dict vazio é
        # honesto sobre o problema em vez de mascarar com `vars(item)`.
        logger.warning(
            "InterruptInfo item não serializável (type=%s); usando {}.",
            type(item).__name__,
        )
        return {}

    return InterruptInfo(
        action_requests=tuple(_serialize(a) for a in action_requests),
        review_configs=tuple(_serialize(c) for c in review_configs),
    )


class LangGraphDirectAgentRunner(AgentRunnerPort):
    """Adapter que compila o grafo `unified` contra um Postgres próprio.

    Cada `run()`:
    1. Abre `AsyncPostgresSaver` + `AsyncPostgresStore` apontando para
       `postgres_uri` (async context managers, fecham ao final).
    2. Compila o grafo via `build_unified(checkpointer=saver, store=store)`.
    3. Chama `graph.ainvoke({"messages": [("user", prompt)]}, config)` com o
       `thread_id` recebido (REQ-003: cria se inexistente, continua se
       existente).
    4. Retorna `AgentRunResult(thread_id, status, error, interrupt=None)`
       ou `AgentRunResult(thread_id, status="interrupted", interrupt=...)`
       quando o grafo pausa num gate `interrupt_on` (REQ-001 do
       `telegram-tool-approval-spec`). Exceções inesperadas viram
       `status="error"` em vez de propagar (o `RunScheduledTask` quer um
       DTO, não uma exceção não-tratada).
    """

    def __init__(self, *, postgres_uri: str) -> None:
        """Guarda a URI do Postgres para abrir o checkpointer/store em cada `run`."""
        self._postgres_uri = postgres_uri

    async def run(
        self,
        *,
        thread_id: str,
        prompt: str,
        skills: tuple[str, ...],
        tool_scope: ToolScope,
        user_key: str | None = None,
    ) -> AgentRunResult:
        """Roda um único turno do agente e devolve um DTO sem exceção.

        `skills` e `tool_scope` são aceitos na assinatura porque o port os
        promete; a integração deles com o `EnvelopeMiddleware` (injeção
        de capabilities, scope de tools) é trabalho de tasks posteriores
        do agendamento-jeff-cli (`task-runtime-2`, `task-tools-1`,
        `task-tests-1`). Aqui só registramos o valor para não perder
        informação quando elas ligarem o port à execução.

        `user_key` entra no `configurable` junto com `thread_id`.
        Metering de chat vem do callback global em `build_unified`
        (track-user-token-usage recording-5).
        """
        logger.debug(
            "LangGraphDirectAgentRunner.run: thread_id=%s scope=%s skills=%d",
            thread_id,
            tool_scope.value,
            len(skills),
        )

        try:
            async with (
                AsyncPostgresSaver.from_conn_string(self._postgres_uri) as saver,
                AsyncPostgresStore.from_conn_string(self._postgres_uri) as store,
            ):
                graph = build_unified(checkpointer=saver, store=store)
                config = _build_run_config(
                    thread_id=thread_id,
                    user_key=user_key,
                )
                state = await graph.ainvoke(
                    {"messages": [("user", prompt)]},
                    config,
                )
        except Exception as exc:  # noqa: BLE001 — DTO precisa de msg, port é a fronteira
            logger.exception(
                "LangGraphDirectAgentRunner.run falhou para thread_id=%s", thread_id
            )
            return AgentRunResult(
                thread_id=thread_id,
                status="error",
                error=str(exc),
            )

        # `telegram-tool-approval` (REQ-001): se o grafo pausou num gate
        # `interrupt_on` esperando decisão humana, `ainvoke` devolve um
        # estado com a chave `__interrupt__` (lista de `Interrupt` cujo
        # `.value` é o `HITLRequest`). Traduzimos isso para
        # `status="interrupted"` + `interrupt=InterruptInfo(...)` para
        # que o `telegram_gateway` apresente a aprovação via teclado
        # inline. Caso contrário, o comportamento é o mesmo de antes:
        # `status="ok"`, `interrupt=None`. `_extract_interrupt` aceita
        # `state | None` (defesa contra `ainvoke` devolver algo
        # exótico) e devolve `None` quando não há pause.
        interrupt_info = _extract_interrupt(state)
        if interrupt_info is not None:
            return AgentRunResult(
                thread_id=thread_id,
                status="interrupted",
                error=None,
                interrupt=interrupt_info,
            )

        return AgentRunResult(thread_id=thread_id, status="ok", error=None)

    async def resume(
        self,
        *,
        thread_id: str,
        decisions: tuple[dict, ...],
        user_key: str | None = None,
    ) -> AgentRunResult:
        """Resumir um grafo pausado num gate `interrupt_on`.

        Chamado pelo `telegram_gateway` (callback handler /
        edit-text intercept) em resposta a uma decisão humana via
        teclado inline. Constrói um `Command(resume={"decisions":
        list(decisions)})` (o shape que o `HumanInTheLoopMiddleware`
        do LangChain espera) e reusa o pipeline de `run()` — mesmo
        checkpointer/store, mesma detecção de `__interrupt__` via
        `_extract_interrupt` — para que um segundo interrupt
        (loop de approval encadeado) apareça como
        `status="interrupted"` no DTO, idêntico ao primeiro.

        Exceções viram `status="error"` (mesma fronteira do `run()`)
        para que o callback handler possa detectar falha via retorno
        em vez de `try/except` no handler — mas, em prática, o
        handler já faz `try/except` por causa do REQ-005 (mesma
        defesa que `run()`).

        `user_key` segue a mesma config de `run()`; o callback de usage
        permanece no grafo (track-user-token-usage recording-5).
        """
        logger.debug(
            "LangGraphDirectAgentRunner.resume: thread_id=%s decisions=%d",
            thread_id,
            len(decisions),
        )

        try:
            async with (
                AsyncPostgresSaver.from_conn_string(self._postgres_uri) as saver,
                AsyncPostgresStore.from_conn_string(self._postgres_uri) as store,
            ):
                graph = build_unified(checkpointer=saver, store=store)
                config = _build_run_config(
                    thread_id=thread_id,
                    user_key=user_key,
                )
                state = await graph.ainvoke(
                    Command(resume={"decisions": list(decisions)}),
                    config,
                )
        except Exception as exc:  # noqa: BLE001 — DTO precisa de msg
            logger.exception(
                "LangGraphDirectAgentRunner.resume falhou para thread_id=%s",
                thread_id,
            )
            return AgentRunResult(
                thread_id=thread_id,
                status="error",
                error=str(exc),
            )

        # Mesma tradução de `__interrupt__` do `run()` — um segundo
        # interrupt (ex.: 2ª rodada de aprovação no mesmo thread) é
        # representável como `status="interrupted"`.
        interrupt_info = _extract_interrupt(state)
        if interrupt_info is not None:
            return AgentRunResult(
                thread_id=thread_id,
                status="interrupted",
                error=None,
                interrupt=interrupt_info,
            )

        return AgentRunResult(thread_id=thread_id, status="ok", error=None)


__all__ = ["LangGraphDirectAgentRunner"]
