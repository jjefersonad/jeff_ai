"""Testes do composition root de canais (task `unify-message-delivery-pipeline-task-composition-1`).

Cobre REQ-002 scenario 1 (chat-channel-port): `build_dependencies()` registra
`WebChannel`, `TelegramChannel` e `WhatsAppChannel` no `ChannelRegistry` do
processo webapp.
"""
from __future__ import annotations

import pytest

from src.composition.dependencies import build_dependencies
from src.domain.channels import ChannelKind
from src.infrastructure.channels.registry import ChannelRegistry
from src.infrastructure.channels.telegram_channel import TelegramChannel
from src.infrastructure.channels.web_channel import WebChannel
from src.infrastructure.channels.whatsapp_channel import WhatsAppChannel


@pytest.fixture(autouse=True)
def _isolated_registry():
    ChannelRegistry.reset()
    yield
    ChannelRegistry.reset()


def test_build_dependencies_registers_web_telegram_and_whatsapp() -> None:
    build_dependencies(
        telegram_bot=object(),
        whatsapp_instance="test-instance",
    )

    web = ChannelRegistry.get(ChannelKind.WEB)
    telegram = ChannelRegistry.get(ChannelKind.TELEGRAM)
    whatsapp = ChannelRegistry.get(ChannelKind.WHATSAPP)

    assert isinstance(web, WebChannel)
    assert isinstance(telegram, TelegramChannel)
    assert isinstance(whatsapp, WhatsAppChannel)
