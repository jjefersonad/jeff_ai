"""Timezone do APScheduler adapter (change fix-get-date-time-current-tz)."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

from src.agents.unified.datetime_utils import _resolve_tz
from src.domain.scheduling import Schedule
from src.infrastructure.scheduling import apscheduler_task_scheduler as mod


def test_scheduler_timezone_delegates_to_resolve_tz(monkeypatch):
    """unit-1 / REQ-ADD-001: sem cópia de env/fallback; usa `_resolve_tz`."""
    source = Path(mod.__file__).read_text(encoding="utf-8")
    assert "from src.agents.unified.datetime_utils import _resolve_tz" in source
    assert "except ZoneInfoNotFoundError" not in source

    monkeypatch.setenv("JEFF_AI_TZ", "America/Sao_Paulo")
    assert mod._scheduler_timezone() == ZoneInfo("America/Sao_Paulo")
    assert mod._scheduler_timezone() == _resolve_tz()

    calls: list[int] = []
    real = _resolve_tz

    def tracking() -> ZoneInfo:
        calls.append(1)
        return real()

    monkeypatch.setattr(mod, "_resolve_tz", tracking)
    mod._scheduler_timezone()
    assert calls, "_scheduler_timezone deve chamar _resolve_tz"


def test_build_trigger_once_sao_paulo_is_utc_11(monkeypatch):
    """unit-2 / REQ-ADD-002: once 08:00 BRT → 11:00 UTC."""
    monkeypatch.setenv("JEFF_AI_TZ", "America/Sao_Paulo")
    trigger = mod._build_trigger(
        Schedule(kind="once", expr="2026-08-07T08:00:00")
    )
    assert isinstance(trigger, DateTrigger)
    assert trigger.run_date is not None
    assert trigger.run_date.astimezone(timezone.utc) == datetime(
        2026, 8, 7, 11, 0, tzinfo=timezone.utc
    )


def test_build_trigger_cron_uses_jeff_ai_tz(monkeypatch):
    """unit-3 / REQ-ADD-003: CronTrigger no mesmo fuso que DateTrigger."""
    monkeypatch.setenv("JEFF_AI_TZ", "America/Sao_Paulo")
    cron = mod._build_trigger(Schedule(kind="cron", expr="0 8 * * *"))
    once = mod._build_trigger(
        Schedule(kind="once", expr="2026-08-07T08:00:00")
    )
    assert isinstance(cron, CronTrigger)
    assert isinstance(once, DateTrigger)
    assert cron.timezone == ZoneInfo("America/Sao_Paulo")
    assert cron.timezone == mod._scheduler_timezone()
    # DateTrigger materializa o fuso no run_date, não em `.timezone`.
    assert once.run_date is not None
    assert once.run_date.tzinfo == cron.timezone
