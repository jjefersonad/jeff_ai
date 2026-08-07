"""Adapter de `TaskSchedulerPort` sobre APScheduler.

Guarda apenas o gatilho (`task.id` + trigger) no `AsyncIOScheduler` — nunca o
contexto de negócio da tarefa (REQ-005 do spec `task-scheduling`; ver design
da mudança `agendamento-jeff-cli`, "Scheduler como relógio, não fonte de
verdade"). Ao disparar, invoca `jeff_cli.py` como subprocesso
(`python -m src.infrastructure.cli.jeff_cli --job-id <id>`) — nunca via
`import`, para não acoplar o tick à disponibilidade do processo da API (ver
design, "Invocação direta do grafo").

`_fire_job` captura stdout/stderr, checa `returncode` e levanta em falha
(fix-scheduled-whatsapp-delivery — evita “executed successfully” cego).
"""
from __future__ import annotations

import asyncio
import logging
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.jobstores.base import JobLookupError
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

from src.agents.unified.datetime_utils import _resolve_tz
from src.application.ports.task_scheduler import TaskSchedulerPort
from src.domain.scheduling import Schedule, ScheduledTask

logger = logging.getLogger(__name__)

_OUTPUT_LOG_LIMIT = 4096


def _scheduler_timezone() -> ZoneInfo:
    """Thin-wrapper sobre `_resolve_tz` (mesmo fuso do prompt e da tool).

    `schedule.expr` de uma tarefa `once` (ex. `"2026-08-04T08:00:00"`) é
    escrito/lido no fuso de `JEFF_AI_TZ` (ver `current-date-context` — é o
    fuso que o agente usa pra "que horas são agora"), não em UTC. Sem passar
    `timezone=` aqui, o `AsyncIOScheduler` cai no fuso local do processo
    (achado empírico: UTC dentro do container Docker), fazendo todo
    agendamento disparar com o offset de `JEFF_AI_TZ` de diferença (3h em
    `America/Sao_Paulo` — uma tarefa "às 8h" disparava às 8h UTC = 5h BRT).
    """
    return _resolve_tz()


class APSchedulerTaskScheduler(TaskSchedulerPort):
    """Registra/remove triggers de `ScheduledTask` num `AsyncIOScheduler`."""

    def __init__(self, scheduler: AsyncIOScheduler | None = None) -> None:
        """Usa `scheduler` se fornecido (testes), senão cria um novo no fuso de `JEFF_AI_TZ`."""
        self._scheduler = scheduler or AsyncIOScheduler(timezone=_scheduler_timezone())

    def start(self) -> None:
        """Inicia o loop de ticks (idempotente)."""
        if not self._scheduler.running:
            self._scheduler.start()

    def shutdown(self, wait: bool = True) -> None:
        """Encerra o loop de ticks (idempotente)."""
        if self._scheduler.running:
            self._scheduler.shutdown(wait=wait)

    async def schedule(self, task: ScheduledTask) -> None:
        """Registra o trigger de `task` (substitui um trigger existente com o mesmo id).

        `misfire_grace_time=3600`: sem jobstore persistente (`MemoryJobStore`
        padrão), todo restart do processo perde os triggers em memória — o
        boot precisa re-registrá-los a partir do Postgres (ver
        `webapp.py:_reschedule_pending_tasks`). Uma janela de reinício curta
        (deploy, crash) não pode fazer uma tarefa `once` cujo horário passou
        por poucos minutos ser descartada silenciosamente pelo misfire padrão
        do APScheduler (1s) — 1h de graça cobre reinícios normais sem
        arriscar disparos muito atrasados.
        """
        self._scheduler.add_job(
            _fire_job,
            trigger=_build_trigger(task.schedule),
            args=[task.id],
            id=task.id,
            replace_existing=True,
            misfire_grace_time=3600,
        )

    async def unschedule(self, task_id: str) -> None:
        """Remove o trigger de `task_id` (no-op se já não existir)."""
        try:
            self._scheduler.remove_job(task_id)
        except JobLookupError:
            pass


def _build_trigger(schedule: Schedule) -> DateTrigger | CronTrigger:
    """Traduz `Schedule` (domínio) para um trigger do APScheduler.

    `DateTrigger`/`CronTrigger` resolvem seu PRÓPRIO `timezone` de forma
    independente do `AsyncIOScheduler` que vai executá-los (default `None` ->
    fuso local do processo) — passar `timezone=` só no construtor do
    scheduler não bastava; sem `timezone=_scheduler_timezone()` aqui também,
    o trigger interpretava `schedule.expr` como UTC mesmo com o scheduler
    configurado em `America/Sao_Paulo` (achado empírico 2026-08-04).
    """
    tz = _scheduler_timezone()
    if schedule.kind == "once":
        return DateTrigger(run_date=datetime.fromisoformat(schedule.expr), timezone=tz)
    minute, hour, day, month, day_of_week = schedule.expr.split()
    return CronTrigger(
        minute=minute,
        hour=hour,
        day=day,
        month=month,
        day_of_week=day_of_week,
        timezone=tz,
    )


def _truncate_output(raw: bytes | None, *, limit: int = _OUTPUT_LOG_LIMIT) -> str:
    """Decodifica e trunca a cauda da saída do subprocesso para log."""
    text = (raw or b"").decode("utf-8", errors="replace")
    if len(text) <= limit:
        return text
    return text[-limit:]


async def _fire_job(task_id: str) -> None:
    """Dispara `jeff_cli.py` como subprocesso; falha alto se exit != 0."""
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "src.infrastructure.cli.jeff_cli",
        "--job-id",
        task_id,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout_b, stderr_b = await proc.communicate()
    returncode = proc.returncode if proc.returncode is not None else -1
    if returncode == 0:
        return

    stdout = _truncate_output(stdout_b)
    stderr = _truncate_output(stderr_b)
    logger.error(
        "jeff_cli_failed task_id=%s returncode=%s stdout=%r stderr=%r",
        task_id,
        returncode,
        stdout,
        stderr,
    )
    raise RuntimeError(
        f"jeff_cli failed for task_id={task_id!r} with returncode={returncode}"
    )
