"""Testes do `ChannelRegistry` (task `unify-message-delivery-pipeline-task-registry-1`).

Verifica REQ-002 (chat-channel-port): `register`/`get` fazem roundtrip por
`ChannelKind`, e `get` de um canal nunca registrado falha rápido — sem
fallback silencioso.
"""
from __future__ import annotations

import pytest

from src.application.ports.chat_channel import ChatChannelPort
from src.domain.channels import ChannelKind, OutputAttachment
from src.infrastructure.channels.registry import ChannelRegistry


class _FakeChannel(ChatChannelPort):
    def __init__(self, kind: ChannelKind) -> None:
        self._kind = kind

    @property
    def channel_kind(self) -> ChannelKind:
        return self._kind

    async def deliver(
        self,
        *,
        user_key: str,
        text: str | None,
        attachments: tuple[OutputAttachment, ...],
        kind: str,
        interrupt: object | None = None,
    ) -> None:
        return None


@pytest.fixture(autouse=True)
def _isolated_registry():
    """`ChannelRegistry` é module-level (um processo real só registra uma
    vez) — testes limpam o estado antes/depois para não vazar entre si."""
    ChannelRegistry.reset()
    yield
    ChannelRegistry.reset()


def test_register_then_get_returns_the_same_adapter() -> None:
    adapter = _FakeChannel(ChannelKind.TELEGRAM)

    ChannelRegistry.register(adapter)

    assert ChannelRegistry.get(ChannelKind.TELEGRAM) is adapter


def test_get_unregistered_kind_raises_runtime_error() -> None:
    with pytest.raises(RuntimeError, match="whatsapp"):
        ChannelRegistry.get(ChannelKind.WHATSAPP)
