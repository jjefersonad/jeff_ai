"""Testes do port `ChatChannelPort` (task `unify-message-delivery-pipeline-task-foundation-3`).

Verifica REQ-001 (chat-channel-port): o contrato abstrato `deliver` e a
aplicação padrão do `ABC` do Python — uma subclasse concreta que implementa
`deliver` instancia; uma que não implementa levanta `TypeError`.
"""
from __future__ import annotations

import pytest

from src.application.ports.chat_channel import ChatChannelPort
from src.domain.channels import ChannelKind, OutputAttachment


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
