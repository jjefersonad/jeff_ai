"""Testes da capability `current-date-context`.

Cobre REQ-001 (data no topo do `_SYSTEM_PROMPT`), REQ-002 (regra sobre quando
chamar `get_date_time_current`), REQ-003 (`_resolve_tz` — TZ válido, inválido,
ausente) e REQ-004 (drift documentado no docstring do módulo).
"""
from __future__ import annotations

import logging
import re
from zoneinfo import ZoneInfo

from src.agents.unified import agent


def test_system_prompt_contains_current_date():
    """REQ-001: a primeira linha do prompt é `Data atual: YYYY-MM-DD (TZ)`."""
    assert agent._SYSTEM_PROMPT.startswith("Data atual: ")
    first_line = agent._SYSTEM_PROMPT.splitlines()[0]
    assert re.match(r"^Data atual: \d{4}-\d{2}-\d{2} \(.+\)$", first_line), first_line


def test_system_prompt_rule_instructs_agente():
    """REQ-002: o prompt instrui a não chamar `get_date_time_current` só para saber o dia."""
    normalized = " ".join(agent._SYSTEM_PROMPT.split())
    assert (
        "Chame `get_date_time_current()` **apenas** se precisar de precisão de "
        "minutos/segundos" in normalized
    )
    assert "use a data no topo do prompt — não custa tool call" in normalized


def test_resolve_tz_with_valid_tz(monkeypatch):
    """REQ-003: TZ IANA válido é resolvido corretamente."""
    monkeypatch.setenv("JEFF_AI_TZ", "America/Sao_Paulo")
    assert agent._resolve_tz() == ZoneInfo("America/Sao_Paulo")


def test_resolve_tz_with_invalid_tz_falls_back_to_utc(monkeypatch, caplog):
    """REQ-003: TZ inválido cai em UTC e loga warning, sem crashar."""
    monkeypatch.setenv("JEFF_AI_TZ", "Atlantis/Lemuria")
    with caplog.at_level(logging.WARNING):
        result = agent._resolve_tz()
    assert result == ZoneInfo("UTC")
    assert any("Atlantis/Lemuria" in record.message for record in caplog.records)


def test_resolve_tz_with_no_env_returns_utc(monkeypatch):
    """REQ-003: sem `JEFF_AI_TZ` no env, o default é UTC."""
    monkeypatch.delenv("JEFF_AI_TZ", raising=False)
    assert agent._resolve_tz() == ZoneInfo("UTC")


def test_drift_documented_in_module_docstring():
    """REQ-004: o drift de data em processos long-running está documentado."""
    doc = agent.__doc__ or ""
    assert "drift" in doc.lower()
    assert "get_date_time_current" in doc
