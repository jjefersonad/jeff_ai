"""Registro de `send_whatsapp_message` após o swap para `send_message`.

A tool por canal saiu do `TIER_REGISTRY` do agente (unify-message-delivery-
pipeline task agent-1). Continua importável como wrapper deprecated
(task cleanup-1); no registry do agente cai no default unknown.
"""
from __future__ import annotations

from src.agents.unified.tier_config import (
    TIER_2_TOOLS,
    TIER_REGISTRY,
    UNKNOWN_TOOL_TIER,
    get_tier,
)

_TOOL_NAME = "send_whatsapp_message"


def test_send_whatsapp_message_is_no_longer_tier_2() -> None:
    assert _TOOL_NAME not in TIER_2_TOOLS
    assert _TOOL_NAME not in TIER_REGISTRY


def test_send_whatsapp_message_falls_to_unknown_tier() -> None:
    assert get_tier(_TOOL_NAME) == UNKNOWN_TOOL_TIER
