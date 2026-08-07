"""Registro de `web_fetch` no unified (add-web-fetch-tool REQ-ADD-001)."""
from __future__ import annotations

from src.agents.unified.effects import Capability, classify
from src.agents.unified.tier_config import TIER_1_TOOLS, build_interrupt_on


def test_web_fetch_in_unified_tools() -> None:
    """Unit-1: web_fetch no flat tool set."""
    from src.agents.unified.agent import _UNIFIED_TOOLS

    names = {
        getattr(t, "name", None) or getattr(t, "__name__", "") for t in _UNIFIED_TOOLS
    }
    assert "web_fetch" in names
    assert "internet_search" in names
    assert "search_arxiv" in names


def test_web_fetch_is_tier_1_not_interrupted() -> None:
    """Unit-2: Tier 1 e fora de interrupt_on."""
    assert "web_fetch" in TIER_1_TOOLS
    gate = build_interrupt_on(list(TIER_1_TOOLS))
    assert "web_fetch" not in gate


def test_web_fetch_effect_network() -> None:
    """Unit-3: effect inclui NETWORK."""
    caps = classify("web_fetch")
    assert Capability.NETWORK in caps


def test_prompt_distinguishes_search_and_fetch() -> None:
    """Prompt: internet_search pesquisa; web_fetch lê URL (REQ-002 delta)."""
    from src.agents.unified.agent import _SYSTEM_PROMPT

    assert "internet_search" in _SYSTEM_PROMPT
    assert "web_fetch" in _SYSTEM_PROMPT
    assert "pesquisar" in _SYSTEM_PROMPT.lower() or "URL" in _SYSTEM_PROMPT
