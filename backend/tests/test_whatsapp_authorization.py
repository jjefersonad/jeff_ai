"""Testes de `src.infrastructure.whatsapp.authorization` (legado + REQ-007).

Após whatsapp-2, o prompt não leva mais pre-prefix de canal. O wrapper
`route_authorized_message` ainda propaga `user_text` cru ao runner.
"""
from __future__ import annotations

from typing import Any

from src.domain.scheduling import ToolScope
from src.infrastructure.whatsapp.authorization import (
    build_channel_prompt,
    route_authorized_message,
)


class _FakeAgentRunner:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.sentinel_result = object()

    async def run(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return self.sentinel_result


def test_build_channel_prompt_returns_user_text_unmodified() -> None:
    assert build_channel_prompt("oi, tudo bem?") == "oi, tudo bem?"
    assert "Canal WhatsApp" not in build_channel_prompt("oi, tudo bem?")


async def test_route_authorized_message_calls_run_with_raw_text() -> None:
    """Wrapper legado: prompt = texto cru (sem CHANNEL_INSTRUCTION)."""
    runner = _FakeAgentRunner()

    result = await route_authorized_message(
        thread_id="thread-xyz",
        text="oi, tudo bem?",
        agent_runner=runner,
        user_key="whatsapp:5511111111111",
    )

    assert len(runner.calls) == 1
    call = runner.calls[0]
    assert call["thread_id"] == "thread-xyz"
    assert call["prompt"] == "oi, tudo bem?"
    assert call["skills"] == ()
    assert call["tool_scope"] == ToolScope.RESTRICTED
    assert call["user_key"] == "whatsapp:5511111111111"
    assert result is runner.sentinel_result
