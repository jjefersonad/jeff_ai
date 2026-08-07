"""Wiring de `preview_html_document` no grafo unified (task-preview-1)."""
from __future__ import annotations

from pathlib import Path

from src.agents.unified.effects import TOOL_EFFECTS, Capability
from src.agents.unified.tier_config import TIER_2_TOOLS


def test_preview_html_document_registered_in_tier2_and_effects() -> None:
    assert "preview_html_document" in TIER_2_TOOLS
    assert "preview_html_document" in TOOL_EFFECTS
    assert Capability.WRITE_NEW in TOOL_EFFECTS["preview_html_document"]


def test_preview_html_document_in_unified_tools_list() -> None:
    agent_src = Path("src/agents/unified/agent.py").read_text(encoding="utf-8")
    list_start = agent_src.index("_UNIFIED_TOOLS: list = [")
    list_end = agent_src.index("]", list_start)
    unified_list = agent_src[list_start:list_end]
    assert "preview_html_document," in unified_list
    assert "preview_html_document" in agent_src
