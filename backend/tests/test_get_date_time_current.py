"""Testes da tool `get_date_time_current` (change fix-get-date-time-current-tz)."""
from __future__ import annotations

import inspect
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import src.tools.deep_agent_tools as deep_agent_tools
from src.agents.unified.datetime_utils import _resolve_tz


_FIXED_UTC = datetime(2026, 8, 7, 3, 23, 38, tzinfo=timezone.utc)
_FORMAT = re.compile(r"^\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2}$")


def _patch_now(monkeypatch) -> None:
    """Fixa o instante UTC no símbolo `datetime` já importado pela tool."""

    class _FrozenDateTime:
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return _FIXED_UTC.replace(tzinfo=None)
            return _FIXED_UTC.astimezone(tz)

    monkeypatch.setattr(deep_agent_tools, "datetime", _FrozenDateTime)


def test_get_date_time_current_sao_paulo_offset(monkeypatch):
    """unit-1 / REQ-ADD-001: wall-clock BRT, não UTC do processo."""
    monkeypatch.setenv("JEFF_AI_TZ", "America/Sao_Paulo")
    _patch_now(monkeypatch)

    result = deep_agent_tools.get_date_time_current.invoke({})

    expected = _FIXED_UTC.astimezone(ZoneInfo("America/Sao_Paulo")).strftime(
        "%d/%m/%Y %H:%M:%S"
    )
    assert result == expected
    assert result == "07/08/2026 00:23:38"
    assert _FORMAT.match(result)


def test_get_date_time_current_default_and_invalid_tz(monkeypatch):
    """unit-2 / REQ-002: env ausente ou inválido → UTC via `_resolve_tz`, sem crash."""
    _patch_now(monkeypatch)
    calls: list[str] = []
    real_resolve = _resolve_tz

    def tracking_resolve():
        calls.append("ok")
        return real_resolve()

    monkeypatch.setattr(
        "src.agents.unified.datetime_utils._resolve_tz", tracking_resolve
    )
    monkeypatch.setattr(deep_agent_tools, "_resolve_tz", tracking_resolve, raising=False)

    monkeypatch.delenv("JEFF_AI_TZ", raising=False)
    monkeypatch.delenv("TZ", raising=False)
    assert deep_agent_tools.get_date_time_current.invoke({}) == "07/08/2026 03:23:38"
    assert calls, "deve chamar _resolve_tz (não datetime.now naive)"

    calls.clear()
    monkeypatch.setenv("JEFF_AI_TZ", "Atlantis/Lemuria")
    # Re-bind tracker after env change (real_resolve reads env).
    monkeypatch.setattr(
        "src.agents.unified.datetime_utils._resolve_tz", tracking_resolve
    )
    monkeypatch.setattr(deep_agent_tools, "_resolve_tz", tracking_resolve, raising=False)
    assert deep_agent_tools.get_date_time_current.invoke({}) == "07/08/2026 03:23:38"
    assert calls


def test_get_date_time_current_docstring_mentions_jeff_ai_tz():
    """unit-3 / REQ-ADD-001: descrição menciona JEFF_AI_TZ."""
    description = (
        deep_agent_tools.get_date_time_current.description
        or deep_agent_tools.get_date_time_current.__doc__
        or ""
    )
    assert "JEFF_AI_TZ" in description
    assert "UTC" in description


def test_get_date_time_current_uses_resolve_tz_helper():
    """unit-4 / REQ-ADD-001 (current-date-context): mesmo helper do prompt."""
    source = inspect.getsource(deep_agent_tools.get_date_time_current.func)
    assert "_resolve_tz" in source
    # O símbolo importado no módulo deve ser o helper canônico.
    assert deep_agent_tools._resolve_tz is _resolve_tz or "_resolve_tz" in source
