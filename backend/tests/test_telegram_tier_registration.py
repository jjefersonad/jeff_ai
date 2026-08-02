"""Testes de registro das tools de Telegram em `tier_config.py`.

Garante REQ-001 (telegram-tools-spec): as três tools de envio
(`send_telegram_message`, `send_telegram_photo`, `send_telegram_document`)
aparecem em Tier 2 e não geram entrada em `interrupt_on` (execução direta,
sem `interrupt_on`).
"""
from __future__ import annotations

from src.agents.unified.tier_config import (
    TIER_2_TOOLS,
    TIER_REGISTRY,
    build_interrupt_on,
)

_TELEGRAM_TOOLS = (
    "send_telegram_message",
    "send_telegram_photo",
    "send_telegram_document",
)


def test_telegram_tools_are_registered_as_tier_2() -> None:
    assert set(_TELEGRAM_TOOLS).issubset(TIER_2_TOOLS)


def test_telegram_tools_have_tier_2_in_registry() -> None:
    for name in _TELEGRAM_TOOLS:
        assert TIER_REGISTRY[name] == 2, f"{name} expected tier 2, got {TIER_REGISTRY[name]}"


def test_telegram_tools_are_not_in_interrupt_on_keys() -> None:
    # O `build_interrupt_on` deny-by-default gera entrada para qualquer tool
    # de tier >= 3; tools de tier 1/2 não entram. Assegura que as três tools
    # de Telegram executam direto (Tier 2) e não geram gate de aprovação.
    interrupt_on = build_interrupt_on(_TELEGRAM_TOOLS)
    for name in _TELEGRAM_TOOLS:
        assert name not in interrupt_on, (
            f"{name} unexpectedly gated in interrupt_on: {interrupt_on.get(name)}"
        )
