"""Testes do port `ChatChannelPort`.

Cobre:
- REQ-001 (chat-channel-port / unify-message-delivery): ABC `deliver` +
  `channel_kind` — subclasse completa instancia; incompleta levanta `TypeError`.
- REQ-001 / REQ-ADD-001 (typing-indicator-chat-channels-task-foundation-1):
  `start_typing_indicator` / `stop_typing_indicator` no ABC; omiti-los
  levanta `TypeError` na instanciação.
"""
from __future__ import annotations

import inspect

import pytest

from src.application.ports.chat_channel import ChatChannelPort
from src.domain.channels import ChannelKind, OutputAttachment
from src.infrastructure.channels.scheduled_channel import ScheduledChannel
from src.infrastructure.channels.web_channel import WebChannel


class _ConcreteChannel(ChatChannelPort):
    def __init__(self) -> None:
        self.calls: list[dict] = []

    @property
    def channel_kind(self) -> ChannelKind:
        return ChannelKind.TELEGRAM

    async def deliver(
        self,
        *,
        user_key: str,
        text: str | None,
        attachments: tuple[OutputAttachment, ...],
        kind: str,
        interrupt: object | None = None,
    ) -> None:
        self.calls.append(
            {
                "user_key": user_key,
                "text": text,
                "attachments": attachments,
                "kind": kind,
                "interrupt": interrupt,
            }
        )

    async def start_typing_indicator(self, *, user_key: str) -> None:
        return None

    async def stop_typing_indicator(self, *, user_key: str) -> None:
        return None


class _IncompleteChannel(ChatChannelPort):
    """Não implementa `deliver` nem `channel_kind` — deve falhar ao instanciar."""


class _MissingChannelKind(ChatChannelPort):
    """Implementa `deliver` mas não `channel_kind` — deve falhar ao instanciar."""

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


class _MissingTypingIndicatorMethods(ChatChannelPort):
    """Implementa `deliver` + `channel_kind` mas não os métodos de typing —
    deve falhar ao instanciar (REQ-001 typing-indicator)."""

    @property
    def channel_kind(self) -> ChannelKind:
        return ChannelKind.TELEGRAM

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


def test_concrete_subclass_implementing_deliver_can_be_instantiated() -> None:
    channel = _ConcreteChannel()

    assert isinstance(channel, ChatChannelPort)


def test_concrete_subclass_exposes_channel_kind() -> None:
    channel = _ConcreteChannel()

    assert channel.channel_kind is ChannelKind.TELEGRAM


async def test_concrete_subclass_deliver_is_callable() -> None:
    channel = _ConcreteChannel()

    await channel.deliver(user_key="telegram:1", text="oi", attachments=(), kind="normal")

    assert channel.calls == [
        {"user_key": "telegram:1", "text": "oi", "attachments": (), "kind": "normal", "interrupt": None}
    ]


def test_subclass_missing_deliver_raises_type_error_on_instantiation() -> None:
    with pytest.raises(TypeError):
        _IncompleteChannel()  # type: ignore[abstract]


def test_subclass_missing_channel_kind_raises_type_error_on_instantiation() -> None:
    with pytest.raises(TypeError):
        _MissingChannelKind()  # type: ignore[abstract]


def test_subclass_missing_typing_indicator_methods_raises_type_error_on_instantiation() -> None:
    with pytest.raises(TypeError):
        _MissingTypingIndicatorMethods()  # type: ignore[abstract]


def test_abstract_methods_include_typing_indicator_methods() -> None:
    assert ChatChannelPort.__abstractmethods__ == frozenset(
        {"channel_kind", "deliver", "start_typing_indicator", "stop_typing_indicator"}
    )


def test_web_channel_and_scheduled_channel_are_concrete() -> None:
    assert inspect.isabstract(WebChannel) is False
    assert inspect.isabstract(ScheduledChannel) is False
