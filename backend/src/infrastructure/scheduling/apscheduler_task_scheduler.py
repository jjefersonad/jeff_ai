"""Adapter de `TaskSchedulerPort` sobre APScheduler.

Guarda apenas o gatilho (`task.id` + trigger) no `AsyncIOScheduler` — nunca o
contexto de negócio da tarefa (REQ-005 do spec `task-scheduling`; ver design
da mudança `agendamento-jeff-cli`, "Scheduler como relógio, não fonte de
verdade"). Ao disparar, invoca `jeff_cli.py` como subprocesso
(`python -m src.infrastructure.cli.jeff_cli --job-id <id>`) — nunca via
`import`, para não acoplar o tick à disponibilidade do processo da API (ver
design, "Invocação direta do grafo").
"""
from __future__ import annotations

import asyncio
import sys
from datetime import datetime

from apscheduler.jobstores.base import JobLookupError
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

from src.application.ports.task_scheduler import TaskSchedulerPort
from src.domain.scheduling import Schedule, ScheduledTask


class APSchedulerTaskScheduler(TaskSchedulerPort):
    """Registra/remove triggers de `ScheduledTask` num `AsyncIOScheduler`."""

    def __init__(self, scheduler: AsyncIOScheduler | None = None) -> None:
        """Usa `scheduler` se fornecido (testes), senão cria um novo."""
        self._scheduler = scheduler or AsyncIOScheduler()

    def start(self) -> None:
        """Inicia o loop de ticks (idempotente)."""
        if not self._scheduler.running:
            self._scheduler.start()

    def shutdown(self, wait: bool = True) -> None:
        """Encerra o loop de ticks (idempotente)."""
        if self._scheduler.running:
            self._scheduler.shutdown(wait=wait)

    async def schedule(self, task: ScheduledTask) -> None:
        """Registra o trigger de `task` (substitui um trigger existente com o mesmo id)."""
        self._scheduler.add_job(
            _fire_job,
            trigger=_build_trigger(task.schedule),
            args=[task.id],
            id=task.id,
            replace_existing=True,
        )

    async def unschedule(self, task_id: str) -> None:
        """Remove o trigger de `task_id` (no-op se já não existir)."""
        try:
            self._scheduler.remove_job(task_id)
        except JobLookupError:
            pass


def _build_trigger(schedule: Schedule) -> DateTrigger | CronTrigger:
    """Traduz `Schedule` (domínio) para um trigger do APScheduler."""
    if schedule.kind == "once":
        return DateTrigger(run_date=datetime.fromisoformat(schedule.expr))
    minute, hour, day, month, day_of_week = schedule.expr.split()
    return CronTrigger(
        minute=minute, hour=hour, day=day, month=month, day_of_week=day_of_week
    )


async def _fire_job(task_id: str) -> None:
    """Dispara `jeff_cli.py` como subprocesso para `task_id` e aguarda o exit."""
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "src.infrastructure.cli.jeff_cli", "--job-id", task_id
    )
    await proc.wait()
