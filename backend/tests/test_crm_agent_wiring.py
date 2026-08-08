"""Wiring CRM tools no grafo unified (add-simple-crm-module-task-agent-1).

Unit-1 (REQ-ADD-001 / REQ-004): tools crm_* no flat set com tiers corretos;
sem subagent/mode crm.
"""
from __future__ import annotations

from src.agents.unified.agent import _TOOL_NAMES, _UNIFIED_SUBAGENTS, _UNIFIED_TOOLS
from src.agents.unified.effects import TOOL_EFFECTS, Capability, classify, needs_grant
from src.agents.unified.tier_config import TIER_REGISTRY, build_interrupt_on

_CRM_READ_TOOLS = (
    "crm_search_contacts",
    "crm_list_deals",
    "crm_list_field_definitions",
)
_CRM_WRITE_TOOLS = (
    "crm_upsert_contact",
    "crm_add_note",
    "crm_create_deal",
    "crm_move_deal",
    "crm_create_field_definition",
    "crm_update_field_definition",
)
_CRM_ALL = _CRM_READ_TOOLS + _CRM_WRITE_TOOLS


def _unified_tool_names() -> set[str]:
    return {
        getattr(t, "name", None) or getattr(t, "__name__", "")
        for t in _UNIFIED_TOOLS
    }


def test_crm_tools_registered_in_flat_set_with_correct_tiers() -> None:
    """unit-1: crm_* em `_UNIFIED_TOOLS` + TIER_REGISTRY; sem interrupt; sem crm subagent."""
    names = _unified_tool_names()
    for tool_name in _CRM_ALL:
        assert tool_name in names, f"{tool_name} missing from _UNIFIED_TOOLS"
        assert tool_name in _TOOL_NAMES

    for tool_name in _CRM_READ_TOOLS:
        assert TIER_REGISTRY.get(tool_name) == 1, tool_name
    for tool_name in _CRM_WRITE_TOOLS:
        assert TIER_REGISTRY.get(tool_name) == 2, tool_name

    interrupt_on = build_interrupt_on(_TOOL_NAMES)
    for tool_name in _CRM_ALL:
        assert tool_name not in interrupt_on, (
            f"{tool_name} should run without interrupt (Tier 1/2)"
        )

    for tool_name in _CRM_READ_TOOLS:
        assert tool_name in TOOL_EFFECTS
        assert classify(tool_name) == (Capability.READ,)
        assert not needs_grant(tool_name)
    for tool_name in _CRM_WRITE_TOOLS:
        assert tool_name in TOOL_EFFECTS
        assert classify(tool_name) == (Capability.WRITE_NEW,)
        assert not needs_grant(tool_name)

    subagent_names = {
        s.get("name") if isinstance(s, dict) else getattr(s, "name", None)
        for s in _UNIFIED_SUBAGENTS
    }
    assert "crm_subagent" not in subagent_names
    assert "crm" not in subagent_names
