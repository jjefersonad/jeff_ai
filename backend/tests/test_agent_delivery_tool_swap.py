"""Testes do swap de tools de entrega no agente (task `agent-1`).

Cobre a proposal / telegram-channel REQ-013 scenario 2: `_UNIFIED_TOOLS`
expõe só `send_message`; `tier_config`/`effects` registram `send_message`
e deixam de tratar as tools por canal como first-class.
"""
from __future__ import annotations

from src.agents.unified import agent as agent_mod
from src.agents.unified.effects import TOOL_EFFECTS, is_unknown
from src.agents.unified.tier_config import TIER_REGISTRY, UNKNOWN_TOOL_TIER, get_tier
from src.tools.delivery_tools import send_message
from src.tools.telegram_tools import send_telegram_message
from src.tools.whatsapp_tools import send_whatsapp_message


def _tool_names() -> set[str]:
    return {
        getattr(t, "name", None) or getattr(t, "__name__", "")
        for t in agent_mod._UNIFIED_TOOLS
    }


def test_unified_tools_contains_send_message_not_channel_specific() -> None:
    names = _tool_names()

    assert send_message in agent_mod._UNIFIED_TOOLS or "send_message" in names
    assert "send_message" in names
    assert "send_telegram_message" not in names
    assert "send_whatsapp_message" not in names
    assert send_telegram_message not in agent_mod._UNIFIED_TOOLS
    assert send_whatsapp_message not in agent_mod._UNIFIED_TOOLS


def test_system_prompt_has_entrega_section_citing_send_message() -> None:
    prompt = agent_mod._SYSTEM_PROMPT

    assert "## Entrega de mensagens" in prompt
    assert "send_message" in prompt
    assert "send_telegram_message" not in prompt
    assert "send_whatsapp_message" not in prompt


def test_tier_and_effects_register_send_message_not_legacy_tools() -> None:
    assert get_tier("send_message") == 2
    assert get_tier("send_message") != UNKNOWN_TOOL_TIER
    assert "send_message" in TIER_REGISTRY
    assert "send_message" in TOOL_EFFECTS

    assert "send_telegram_message" not in TIER_REGISTRY
    assert "send_whatsapp_message" not in TIER_REGISTRY
    assert "send_telegram_message" not in TOOL_EFFECTS
    # WhatsApp nunca esteve em TOOL_EFFECTS; permanece unknown se consultado.
    assert is_unknown("send_whatsapp_message")
    assert get_tier("send_telegram_message") == UNKNOWN_TOOL_TIER
    assert get_tier("send_whatsapp_message") == UNKNOWN_TOOL_TIER
