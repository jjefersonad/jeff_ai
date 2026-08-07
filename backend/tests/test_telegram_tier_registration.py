"""Testes de registro das tools de Telegram em `tier_config.py`.

`send_telegram_message` saiu do registry do agente (substituída por
`send_message` — unify-message-delivery-pipeline task agent-1). Restam
photo/document em Tier 2, sem `interrupt_on`.
"""
from __future__ import annotations

from src.agents.unified.tier_config import (
    TIER_2_TOOLS,
    TIER_REGISTRY,
    build_interrupt_on,
)

_TELEGRAM_MEDIA_TOOLS = (
    "send_telegram_photo",
    "send_telegram_document",
)


def test_telegram_media_tools_are_registered_as_tier_2() -> None:
    assert set(_TELEGRAM_MEDIA_TOOLS).issubset(TIER_2_TOOLS)


def test_telegram_media_tools_have_tier_2_in_registry() -> None:
    for name in _TELEGRAM_MEDIA_TOOLS:
        assert TIER_REGISTRY[name] == 2, f"{name} expected tier 2, got {TIER_REGISTRY[name]}"


def test_telegram_media_tools_are_not_in_interrupt_on_keys() -> None:
    interrupt_on = build_interrupt_on(_TELEGRAM_MEDIA_TOOLS)
    for name in _TELEGRAM_MEDIA_TOOLS:
        assert name not in interrupt_on, (
            f"{name} unexpectedly gated in interrupt_on: {interrupt_on.get(name)}"
        )


def test_send_telegram_message_is_no_longer_first_class_tier_entry() -> None:
    assert "send_telegram_message" not in TIER_2_TOOLS
    assert "send_telegram_message" not in TIER_REGISTRY
