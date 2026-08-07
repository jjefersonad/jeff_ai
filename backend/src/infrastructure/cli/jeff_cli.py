"""Entrypoint do subprocesso `jeff_cli` (task `agendamento-jeff-cli-task-runtime-2`).

Disparado pelo `APSchedulerTaskScheduler` como `python -m
src.infrastructure.cli.jeff_cli --job-id <id>`: roda uma única
`ScheduledTask` sem depender do processo HTTP do servidor estar de pé (ver
design da mudança `agendamento-jeff-cli`, "Invocação direta do grafo").

Humble Object: este módulo só faz parsing de argv, monta o composition root
(`ChannelRegistry` ← `ScheduledChannel` + `WebChannel` e, se houver env,
Telegram/WhatsApp; `PostgresScheduledTaskRepository`
+ `LangGraphDirectAgentRunner` → `RunScheduledTask`) e traduz o status final
da tarefa em exit code (jeff-cli REQ-004: 0 em sucesso, != 0 em
falha/timeout/tarefa que não terminou SUCCEEDED). Toda decisão de negócio
(máquina de estado, timeout) fica em `RunScheduledTask`.

`_build_components` isola os imports pesados (psycopg, LangGraph) — assim
um `--job-id` ausente falha imediatamente via `argparse`, sem pagar o custo
de importar a stack inteira do grafo.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os

from src.application.ports.scheduled_task_repository import ScheduledTaskRepositoryPort
from src.application.use_cases.run_scheduled_task import RunScheduledTask
from src.composition.env import load_env
from src.domain.scheduling import TaskStatus
from src.infrastructure.channels.registry import ChannelRegistry
from src.infrastructure.channels.scheduled_channel import ScheduledChannel
from src.infrastructure.channels.web_channel import WebChannel

logger = logging.getLogger(__name__)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parseia `--job-id` (obrigatório) do argv."""
    parser = argparse.ArgumentParser(prog="jeff_cli")
    parser.add_argument("--job-id", required=True, dest="job_id")
    return parser.parse_args(argv)


async def _noop_web_emit(_payload: dict) -> None:
    """Sink no-op: o subprocesso do job não tem SSE web."""
    return None


def _register_channels() -> None:
    """Popula o `ChannelRegistry` deste subprocesso (REQ-005 targeting).

    Sempre: `ScheduledChannel` (delegator) + `WebChannel` (emit no-op — o
    job não tem SSE; evita `canal web não registrado` no notify).
    Condicional: Telegram/WhatsApp só quando as envs de credencial existem,
    para o boot não depender de tokens em jobs que não os usam.
    """
    ChannelRegistry.register(ScheduledChannel())
    ChannelRegistry.register(WebChannel(emit=_noop_web_emit))

    telegram_token = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    if telegram_token:
        from telegram import Bot

        from src.infrastructure.channels.telegram_channel import TelegramChannel

        ChannelRegistry.register(TelegramChannel(bot=Bot(token=telegram_token)))

    whatsapp_instance = (os.environ.get("EVOLUTION_INSTANCE_NAME") or "").strip()
    if whatsapp_instance:
        from src.infrastructure.channels.whatsapp_channel import WhatsAppChannel

        ChannelRegistry.register(WhatsAppChannel(instance=whatsapp_instance))

def _build_components(
    postgres_uri: str,
) -> tuple[ScheduledTaskRepositoryPort, RunScheduledTask]:
    """Monta o composition root: repositório + agent runner → `RunScheduledTask`.

    Importação lazy dos adapters concretos (psycopg, LangGraph) — só paga o
    custo depois que `POSTGRES_URI` já foi validado.
    """
    from src.application.use_cases.handle_chat_message import HandleChatMessage
    from src.infrastructure.agent_runtime.langgraph_direct_runner import (
        LangGraphDirectAgentRunner,
    )
    from src.infrastructure.channels.scheduled_channel import ScheduledChannel
    from src.infrastructure.persistence.scheduled_task_repository import (
        PostgresScheduledTaskRepository,
    )

    repository = PostgresScheduledTaskRepository(postgres_uri)
    agent_runner = LangGraphDirectAgentRunner(postgres_uri=postgres_uri)
    return repository, RunScheduledTask(
        repository=repository,
        agent_runner=agent_runner,
        handle_chat_message=HandleChatMessage(agent_runner=agent_runner),
        notify_channel=ScheduledChannel(),
    )


async def _run(
    *,
    job_id: str,
    components: tuple[ScheduledTaskRepositoryPort, RunScheduledTask],
) -> int:
    """Executa `job_id` e traduz o status final em exit code (REQ-004).

    `SUCCEEDED`, cron rearmado (`SCHEDULED` após o tick — Decision 5) ou
    tarefa inexistente (no-op tolerante) → 0. `FAILED` (once),
    `WAITING_HUMAN`, `RUNNING` ou outros → 1.
    """
    repository, use_case = components
    await use_case.execute(task_id=job_id)

    task = await repository.get(job_id)
    if task is None or task.status in (
        TaskStatus.SUCCEEDED,
        TaskStatus.SCHEDULED,
    ):
        return 0
    return 1


def main(argv: list[str] | None = None) -> int:
    """Entry-point síncrono: parse argv, valida env, roda o job, devolve exit code."""
    load_env()
    args = parse_args(argv)

    postgres_uri = os.environ.get("POSTGRES_URI")
    if not postgres_uri:
        logger.error("POSTGRES_URI não está configurado (esperada em ./.env).")
        return 1

    _register_channels()
    components = _build_components(postgres_uri)
    return asyncio.run(_run(job_id=args.job_id, components=components))


if __name__ == "__main__":
    raise SystemExit(main())
