"""Guard REQ-006 (saas-empresario-br-task-guard-1): sem modo empresário
e sem subagente de onboarding no grafo unified.
"""
from __future__ import annotations

from src.agents.unified.agent import _UNIFIED_SUBAGENTS


def test_unified_subagents_nao_inclui_onboarding_nem_empresario() -> None:
    """REQ-006: nenhum subagente registrado cujo trabalho seja onboarding."""
    names = {
        ((s.get("name") if isinstance(s, dict) else getattr(s, "name", None)) or "")
        for s in _UNIFIED_SUBAGENTS
    }
    for name in names:
        lowered = name.lower()
        assert "onboarding" not in lowered
        assert "empresario" not in lowered
        assert "empresário" not in lowered
