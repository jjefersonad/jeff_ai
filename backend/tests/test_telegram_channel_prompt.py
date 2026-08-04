"""Testes de `build_channel_prompt` sem pre-prefix (task
`unify-message-delivery-pipeline-task-telegram-2`).

Cobre REQ-013 (telegram-channel): sem `CHANNEL_INSTRUCTION` / "Canal Telegram".
"""
from __future__ import annotations

from src.infrastructure.telegram import authorization


def test_build_channel_prompt_returns_user_text_unmodified() -> None:
    """Unit-1: `build_channel_prompt("oi")` devolve exatamente `"oi"`."""
    assert authorization.build_channel_prompt("oi") == "oi"
    assert "Canal Telegram" not in authorization.build_channel_prompt("oi")


def test_channel_instruction_constant_removed() -> None:
    """REQ-013: constante `CHANNEL_INSTRUCTION` não existe mais no módulo."""
    assert not hasattr(authorization, "CHANNEL_INSTRUCTION")
