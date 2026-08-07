"""Testes de `APSchedulerTaskScheduler` (task `agendamento-jeff-cli-task-scheduling-infra-1`).

Cobre os critérios de aceite da task:
- REQ-003: `schedule(task)` registra o trigger correto (cron/interval/once) a partir de `task.schedule`
- REQ-005: guarda apenas `(trigger, task_id)` — nenhum campo de negócio da tarefa é passado ao APScheduler
- Dispara `jeff_cli.py` via subprocesso (`python -m ...`), nunca via `import`
- `unschedule(task_id)` remove o job sem erro se já não existir
- Integração leve: agenda trigger "daqui a 1s", confirma que o subprocesso dispara
"""
from __future__ import annotations

import asyncio
import re
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

from src.domain.scheduling import Schedule, ScheduledTask


def _new_task(**overrides: object) -> ScheduledTask:
    kwargs: dict[str, object] = {
        "id": "t-1",
        "prompt": "diga olá",
        "thread_id": "th-1",
        "schedule": Schedule(kind="once", expr="2026-12-31T23:59:00"),
        "owner_user_key": "web:owner-1",
    }
    kwargs.update(overrides)
    return ScheduledTask(**kwargs)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# REQ-003 — trigger correto a partir de task.schedule
# ---------------------------------------------------------------------------


async def test_schedule_registers_date_trigger_for_once():
    from src.infrastructure.scheduling.apscheduler_task_scheduler import (
        APSchedulerTaskScheduler,
    )

    scheduler = APSchedulerTaskScheduler()
    task = _new_task(schedule=Schedule(kind="once", expr="2026-12-31T23:59:00"))

    await scheduler.schedule(task)

    job = scheduler._scheduler.get_job(task.id)
    assert job is not None
    assert isinstance(job.trigger, DateTrigger)


async def test_schedule_registers_cron_trigger_for_cron():
    from src.infrastructure.scheduling.apscheduler_task_scheduler import (
        APSchedulerTaskScheduler,
    )

    scheduler = APSchedulerTaskScheduler()
    task = _new_task(schedule=Schedule(kind="cron", expr="0 9 * * *"))

    await scheduler.schedule(task)

    job = scheduler._scheduler.get_job(task.id)
    assert job is not None
    assert isinstance(job.trigger, CronTrigger)


async def test_schedule_is_idempotent_replaces_existing_job():
    from src.infrastructure.scheduling.apscheduler_task_scheduler import (
        APSchedulerTaskScheduler,
    )

    scheduler = APSchedulerTaskScheduler()
    scheduler.start()
    try:
        task = _new_task(schedule=Schedule(kind="once", expr="2026-12-31T23:59:00"))
        await scheduler.schedule(task)

        task_again = _new_task(schedule=Schedule(kind="cron", expr="0 9 * * *"))
        await scheduler.schedule(task_again)

        job = scheduler._scheduler.get_job(task.id)
        assert isinstance(job.trigger, CronTrigger)
        assert len(scheduler._scheduler.get_jobs()) == 1
    finally:
        scheduler.shutdown(wait=False)


# ---------------------------------------------------------------------------
# REQ-005 — só (trigger, task_id) chega ao APScheduler
# ---------------------------------------------------------------------------


async def test_scheduled_job_args_carry_only_task_id():
    from src.infrastructure.scheduling.apscheduler_task_scheduler import (
        APSchedulerTaskScheduler,
    )

    scheduler = APSchedulerTaskScheduler()
    task = _new_task(prompt="segredo de negócio", thread_id="th-secreto")

    await scheduler.schedule(task)

    job = scheduler._scheduler.get_job(task.id)
    assert job.args == (task.id,)
    assert job.kwargs == {}


# ---------------------------------------------------------------------------
# Dispara via subprocesso `python -m ...`, nunca via import
# ---------------------------------------------------------------------------


def test_module_never_imports_jeff_cli_directly():
    src = (
        Path(__file__).parent.parent
        / "src"
        / "infrastructure"
        / "scheduling"
        / "apscheduler_task_scheduler.py"
    ).read_text()
    no_strings = re.sub(r'""".*?"""', "", src, flags=re.DOTALL)
    assert not re.search(
        r"^\s*(import|from)\s+.*jeff_cli", no_strings, flags=re.MULTILINE
    ), "apscheduler_task_scheduler.py não pode importar jeff_cli — disparo é via subprocesso"


async def test_fire_job_invokes_jeff_cli_as_subprocess_module(monkeypatch):
    from src.infrastructure.scheduling import apscheduler_task_scheduler as mod

    captured: dict[str, object] = {}

    async def fake_create_subprocess_exec(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs

        class _FakeProc:
            returncode = 0

            async def communicate(self) -> tuple[bytes, bytes]:
                return b"", b""

        return _FakeProc()

    monkeypatch.setattr(
        asyncio, "create_subprocess_exec", fake_create_subprocess_exec
    )

    await mod._fire_job("t-fire-1")

    assert captured["args"] == (
        sys.executable,
        "-m",
        "src.infrastructure.cli.jeff_cli",
        "--job-id",
        "t-fire-1",
    )
    assert captured["kwargs"].get("stdout") is asyncio.subprocess.PIPE
    assert captured["kwargs"].get("stderr") is asyncio.subprocess.PIPE


async def test_fire_job_nonzero_returncode_raises_and_logs(monkeypatch, caplog):
    """fire-1 unit-1: returncode != 0 → log + RuntimeError (não quiet success)."""
    import logging

    from src.infrastructure.scheduling import apscheduler_task_scheduler as mod

    async def fake_create_subprocess_exec(*args, **kwargs):
        class _FakeProc:
            returncode = 1

            async def communicate(self) -> tuple[bytes, bytes]:
                return b"stdout-out", b"stderr-out"

        return _FakeProc()

    monkeypatch.setattr(
        asyncio, "create_subprocess_exec", fake_create_subprocess_exec
    )

    with caplog.at_level(logging.ERROR):
        try:
            await mod._fire_job("t-fail-1")
            raised = False
        except RuntimeError as exc:
            raised = True
            assert "t-fail-1" in str(exc)
            assert "1" in str(exc)

    assert raised
    assert any(
        "t-fail-1" in r.message and "returncode" in r.message
        for r in caplog.records
        if r.levelno == logging.ERROR
    )


async def test_fire_job_zero_returncode_succeeds_quietly(monkeypatch, caplog):
    """fire-1 unit-2: returncode == 0 → sem raise e sem log de erro de subprocesso."""
    import logging

    from src.infrastructure.scheduling import apscheduler_task_scheduler as mod

    async def fake_create_subprocess_exec(*args, **kwargs):
        class _FakeProc:
            returncode = 0

            async def communicate(self) -> tuple[bytes, bytes]:
                return b"ok", b""

        return _FakeProc()

    monkeypatch.setattr(
        asyncio, "create_subprocess_exec", fake_create_subprocess_exec
    )

    with caplog.at_level(logging.ERROR):
        await mod._fire_job("t-ok-1")

    assert not any(
        "returncode" in r.message or "jeff_cli" in r.message
        for r in caplog.records
        if r.levelno >= logging.ERROR
    )


# ---------------------------------------------------------------------------
# unschedule(task_id) — no-op tolerante
# ---------------------------------------------------------------------------


async def test_unschedule_removes_job():
    from src.infrastructure.scheduling.apscheduler_task_scheduler import (
        APSchedulerTaskScheduler,
    )

    scheduler = APSchedulerTaskScheduler()
    task = _new_task()
    await scheduler.schedule(task)
    assert scheduler._scheduler.get_job(task.id) is not None

    await scheduler.unschedule(task.id)

    assert scheduler._scheduler.get_job(task.id) is None


async def test_unschedule_missing_job_is_noop():
    from src.infrastructure.scheduling.apscheduler_task_scheduler import (
        APSchedulerTaskScheduler,
    )

    scheduler = APSchedulerTaskScheduler()

    await scheduler.unschedule("nao-existe")  # não deve levantar exceção


# ---------------------------------------------------------------------------
# Integração leve: agenda "daqui a 1s", confirma que o subprocesso dispara
# ---------------------------------------------------------------------------


async def test_schedule_fires_subprocess_after_one_second(monkeypatch):
    from src.infrastructure.scheduling.apscheduler_task_scheduler import (
        APSchedulerTaskScheduler,
    )

    calls: list[tuple[object, ...]] = []

    async def fake_create_subprocess_exec(*args, **kwargs):
        calls.append(args)

        class _FakeProc:
            returncode = 0

            async def communicate(self) -> tuple[bytes, bytes]:
                return b"", b""

        return _FakeProc()

    monkeypatch.setattr(
        asyncio, "create_subprocess_exec", fake_create_subprocess_exec
    )

    scheduler = APSchedulerTaskScheduler()
    scheduler.start()
    try:
        run_at = datetime.now(UTC) + timedelta(seconds=1)
        task = _new_task(
            id="t-fire-2",
            schedule=Schedule(kind="once", expr=run_at.isoformat()),
        )
        await scheduler.schedule(task)

        await asyncio.sleep(1.5)
    finally:
        scheduler.shutdown(wait=False)

    assert len(calls) == 1
    assert calls[0][-1] == "t-fire-2"
