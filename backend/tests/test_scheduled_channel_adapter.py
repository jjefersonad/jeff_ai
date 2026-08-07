"""Testes do adapter `ScheduledChannel` (task `unify-message-delivery-pipeline-task-adapters-4`).

Cobre REQ-010 (scheduled-tasks) / REQ-004 (chat-channel-port): resolve o
canal primário do owner a partir do `user_key` e delega a entrega — sem
fallback silencioso quando o canal não é resolvível ou não está registrado
neste processo.
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.domain.channels import ChannelKind
from src.infrastructure.channels.registry import ChannelRegistry
from src.infrastructure.channels.scheduled_channel import ScheduledChannel


@pytest.fixture(autouse=True)
def _isolated_registry():
    ChannelRegistry.reset()
    yield
    ChannelRegistry.reset()


def test_channel_kind_is_scheduled() -> None:
    channel = ScheduledChannel()

    assert channel.channel_kind is ChannelKind.SCHEDULED


@pytest.mark.asyncio
async def test_deliver_delegates_to_resolved_channel() -> None:
    telegram_channel = AsyncMock()
    telegram_channel.channel_kind = ChannelKind.TELEGRAM
    ChannelRegistry.register(telegram_channel)
    channel = ScheduledChannel()

    await channel.deliver(user_key="telegram:1234", text="Resultado", attachments=(), kind="normal")

    telegram_channel.deliver.assert_awaited_once_with(
        user_key="telegram:1234",
        text="Resultado",
        attachments=(),
        kind="normal",
        interrupt=None,
        thread_id=None,
    )


@pytest.mark.asyncio
async def test_deliver_unresolvable_user_key_raises_runtime_error() -> None:
    channel = ScheduledChannel()

    with pytest.raises(RuntimeError, match="não está mais disponível"):
        await channel.deliver(user_key=None, text="oi", attachments=(), kind="normal")

    with pytest.raises(RuntimeError, match="não está mais disponível"):
        await channel.deliver(user_key="unknown", text="oi", attachments=(), kind="normal")


@pytest.mark.asyncio
async def test_deliver_resolved_channel_not_registered_raises_runtime_error() -> None:
    channel = ScheduledChannel()

    with pytest.raises(RuntimeError, match="telegram"):
        await channel.deliver(user_key="telegram:1234", text="oi", attachments=(), kind="normal")


@pytest.mark.asyncio
async def test_start_typing_indicator_is_a_noop_and_does_not_resolve_registry() -> None:
    channel = ScheduledChannel()

    result = await channel.start_typing_indicator(user_key="telegram:1234")

    assert result is None
    with pytest.raises(RuntimeError, match="não registrado"):
        ChannelRegistry.get(ChannelKind.TELEGRAM)


@pytest.mark.asyncio
async def test_stop_typing_indicator_is_a_noop_and_does_not_resolve_registry() -> None:
    channel = ScheduledChannel()

    result = await channel.stop_typing_indicator(user_key="telegram:1234")

    assert result is None
    with pytest.raises(RuntimeError, match="não registrado"):
        ChannelRegistry.get(ChannelKind.TELEGRAM)
