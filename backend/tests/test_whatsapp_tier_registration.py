"""Teste de registro de `send_whatsapp_message` em `tier_config.py`.

Garante REQ-001 (whatsapp-tools-spec): a tool aparece em Tier 2 e não gera
entrada em `interrupt_on` (execução direta, sem `interrupt_on`) — mesmo
padrão de `test_telegram_tier_registration.py`.
"""
from __future__ import annotations

from src.agents.unified.tier_config import (
    TIER_2_TOOLS,
    TIER_REGISTRY,
    build_interrupt_on,
)

_TOOL_NAME = "send_whatsapp_message"


def test_send_whatsapp_message_is_registered_as_tier_2() -> None:
    """whatsapp-evolution-channel-task-tools-2-unit-1."""
    assert _TOOL_NAME in TIER_2_TOOLS


def test_send_whatsapp_message_has_tier_2_in_registry() -> None:
    assert TIER_REGISTRY[_TOOL_NAME] == 2, (
        f"{_TOOL_NAME} expected tier 2, got {TIER_REGISTRY[_TOOL_NAME]}"
    )


def test_send_whatsapp_message_is_not_in_interrupt_on_keys() -> None:
    interrupt_on = build_interrupt_on((_TOOL_NAME,))
    assert _TOOL_NAME not in interrupt_on, (
        f"{_TOOL_NAME} unexpectedly gated in interrupt_on: {interrupt_on.get(_TOOL_NAME)}"
    )
