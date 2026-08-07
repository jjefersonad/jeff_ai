"""Wiring de `create_pdf_document` no grafo unified (task-wire-1)."""
from __future__ import annotations

from pathlib import Path

from src.agents.unified.effects import TOOL_EFFECTS, Capability
from src.agents.unified.tier_config import TIER_2_TOOLS


def test_create_pdf_document_registered_in_tier2_and_effects() -> None:
    """Unit: tool no registry unified / Tier 2 / effects."""
    assert "create_pdf_document" in TIER_2_TOOLS
    assert "create_pdf_document" in TOOL_EFFECTS
    assert Capability.WRITE_NEW in TOOL_EFFECTS["create_pdf_document"]

    agent_src = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "agents"
        / "unified"
        / "agent.py"
    ).read_text(encoding="utf-8")
    # Ancora na atribuição da lista (evita menções em docstrings anteriores).
    list_start = agent_src.index("_UNIFIED_TOOLS: list = [")
    list_end = agent_src.index("_UNIFIED_SUBAGENTS: list = [", list_start)
    unified_list = agent_src[list_start:list_end]
    assert "create_pdf_document," in unified_list
    assert "create_pdf_document" in agent_src  # também citado no prompt
