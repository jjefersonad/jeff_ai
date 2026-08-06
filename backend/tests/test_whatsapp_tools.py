"""Testes de `src/tools/whatsapp_tools.py` (wrappers deprecated pós-cleanup-1).

A tool agora delega a `ChannelRegistry` → `WhatsAppChannel.deliver`.
Resolução de vínculo (destino implícito) e erro sem vínculo permanecem.
"""
from __future__ import annotations

import pytest

from src.application.ports.agent_runner import InterruptInfo
from src.application.ports.chat_channel import ChatChannelPort, DeliveryKind
from src.domain.channels import ChannelKind, OutputAttachment
from src.domain.integrations import UserIntegration
from src.infrastructure.channels.registry import ChannelRegistry
from src.tools import whatsapp_tools


class _RecordingChannel(ChatChannelPort):
    def __init__(self) -> None:
        self.calls: list[dict] = []

    @property
    def channel_kind(self) -> ChannelKind:
        return ChannelKind.WHATSAPP

    async def deliver(
        self,
        *,
        user_key: str,
        text: str | None,
        attachments: tuple[OutputAttachment, ...],
        kind: DeliveryKind,
        interrupt: InterruptInfo | None = None,
        thread_id: str | None = None,
    ) -> None:
        self.calls.append({"user_key": user_key, "text": text, "kind": kind})

    async def start_typing_indicator(self, *, user_key: str) -> None:
        return None

    async def stop_typing_indicator(self, *, user_key: str) -> None:
        return None


@pytest.fixture(autouse=True)
def _isolated_registry():
    ChannelRegistry.reset()
    yield
    ChannelRegistry.reset()


def _whatsapp_integration(*, user_id: str, phone_number: str) -> UserIntegration:
    return UserIntegration(
        id="integration-1",
        user_id=user_id,
        integration_type="whatsapp_business",
        config={"phone_number": phone_number},
    )


def _patch_resolve_user_id(monkeypatch: pytest.MonkeyPatch, user_id: str | None) -> None:
    async def _fake_resolve_user_id() -> str | None:
        return user_id

    monkeypatch.setattr(whatsapp_tools, "resolve_user_id", _fake_resolve_user_id)


def _patch_integration_repository(
    monkeypatch: pytest.MonkeyPatch, integrations: list[UserIntegration]
) -> None:
    class _FakeRepository:
        def __init__(self, conninfo: str) -> None:
            self.conninfo = conninfo

        async def list_by_user(self, user_id: str) -> list[UserIntegration]:
            return [i for i in integrations if i.user_id == user_id]

    monkeypatch.setattr(whatsapp_tools, "PostgresUserIntegrationRepository", _FakeRepository)
    monkeypatch.setenv("POSTGRES_URI", "postgresql://fake")


async def test_send_whatsapp_message_without_destination_uses_linked_phone_number(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """whatsapp-evolution-channel-task-tools-2-unit-2 (via ChannelRegistry)."""
    _patch_resolve_user_id(monkeypatch, "user-xyz")
    _patch_integration_repository(
        monkeypatch, [_whatsapp_integration(user_id="user-xyz", phone_number="5511999990000")]
    )
    channel = _RecordingChannel()
    ChannelRegistry.register(channel)

    result = await whatsapp_tools.send_whatsapp_message.ainvoke({"text": "oi"})

    assert result["success"] is True
    assert channel.calls == [
        {"user_key": "whatsapp:5511999990000", "text": "oi", "kind": "normal"}
    ]


async def test_send_whatsapp_message_without_link_returns_error_without_calling_channel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """whatsapp-evolution-channel-task-tools-2-unit-3."""
    _patch_resolve_user_id(monkeypatch, "user-xyz")
    _patch_integration_repository(monkeypatch, [])
    channel = _RecordingChannel()
    ChannelRegistry.register(channel)

    result = await whatsapp_tools.send_whatsapp_message.ainvoke({"text": "oi"})

    assert result["success"] is False
    assert channel.calls == []


async def test_send_whatsapp_message_without_session_user_returns_error_without_calling_channel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_resolve_user_id(monkeypatch, None)
    channel = _RecordingChannel()
    ChannelRegistry.register(channel)

    result = await whatsapp_tools.send_whatsapp_message.ainvoke({"text": "oi"})

    assert result["success"] is False
    assert channel.calls == []


async def test_send_whatsapp_message_with_explicit_destination_ignores_link(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _explode(conninfo: str) -> None:
        raise AssertionError("destino explícito não deveria consultar user_integrations")

    monkeypatch.setattr(whatsapp_tools, "PostgresUserIntegrationRepository", _explode)
    channel = _RecordingChannel()
    ChannelRegistry.register(channel)

    result = await whatsapp_tools.send_whatsapp_message.ainvoke(
        {"text": "oi", "phone_number": "5511888880000"}
    )

    assert result["success"] is True
    assert channel.calls == [
        {"user_key": "whatsapp:5511888880000", "text": "oi", "kind": "normal"}
    ]
