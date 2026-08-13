"""crm_create_deal contact kwargs + lead tools gone (backend-agent-1)."""
from __future__ import annotations

import pytest

import src.tools.crm_tools as ct
from src.agents.unified.agent import _SYSTEM_PROMPT, _TOOL_NAMES, _UNIFIED_TOOLS
from src.agents.unified.effects import TOOL_EFFECTS
from src.agents.unified.tier_config import TIER_REGISTRY, build_interrupt_on
from src.application.use_cases.create_crm_deal import CreateCrmDeal
from test_crm_tools import _FakeCrmRepository, _stub_resolved_user_id

_LEAD_TOOLS = ("crm_create_lead", "crm_convert_lead")


def _unified_tool_names() -> set[str]:
    return {
        getattr(t, "name", None) or getattr(t, "__name__", "")
        for t in _UNIFIED_TOOLS
    }


def test_lead_tools_absent_from_unified_graph() -> None:
    """unit-1: crm_create_lead / crm_convert_lead not in tools, prompt, tiers."""
    names = _unified_tool_names()
    for tool_name in _LEAD_TOOLS:
        assert tool_name not in names
        assert tool_name not in _TOOL_NAMES
        assert tool_name not in _SYSTEM_PROMPT
        assert tool_name not in TIER_REGISTRY
        assert tool_name not in TOOL_EFFECTS


async def test_crm_create_deal_with_contact_kwargs_creates_both(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """unit-2: title + email/phone kwargs → deal and contact linked in one call."""
    _stub_resolved_user_id(monkeypatch, "user-a")
    repo = _FakeCrmRepository()
    monkeypatch.setattr(
        ct, "build_create_crm_deal", lambda: CreateCrmDeal(repository=repo)
    )

    result = await ct.crm_create_deal.ainvoke(
        {
            "title": "Acme",
            "contact_name": "João",
            "email": "joao@acme.com",
            "phone": "11999998888",
        }
    )

    assert "error" not in result
    assert result["contact_id"] is not None
    contact = repo.contacts[result["contact_id"]]
    assert contact.name == "João"
    assert contact.email == "joao@acme.com"
    assert contact.phone == "11999998888"
    assert len(repo.deals) == 1
    assert len(repo.contacts) == 1


def test_crm_create_deal_and_move_remain_tier_2() -> None:
    """unit-3: crm_create_deal and crm_move_deal stay Tier 2, not in interrupt_on."""
    assert TIER_REGISTRY["crm_create_deal"] == 2
    assert TIER_REGISTRY["crm_move_deal"] == 2
    interrupt_on = build_interrupt_on(_TOOL_NAMES)
    assert "crm_create_deal" not in interrupt_on
    assert "crm_move_deal" not in interrupt_on
