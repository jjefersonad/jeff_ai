"""Testes da tool `send_message` (task `unify-message-delivery-pipeline-task-delivery-1`).

Cobre REQ-001/REQ-002 (chat-channel-port): a tool resolve o canal via
`configurable.user_key`, busca o adapter no `ChannelRegistry` e delega a
`deliver`. Erros de registry propagam (não são engolidos) — caminho
explícito do agente, distinto da auto-captura fail-safe.
"""
from __future__ import annotations

import pytest

from src.application.ports.chat_channel import ChatChannelPort, DeliveryKind
from src.application.ports.agent_runner import InterruptInfo
from src.domain.channels import ChannelKind, OutputAttachment
from src.infrastructure.channels.registry import ChannelRegistry
from src.tools import delivery_tools as dt


class _RecordingChannel(ChatChannelPort):
    def __init__(self, kind: ChannelKind = ChannelKind.TELEGRAM) -> None:
        self._kind = kind
        self.calls: list[dict] = []

    @property
    def channel_kind(self) -> ChannelKind:
        return self._kind

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
        self.calls.append(
            {
                "user_key": user_key,
                "text": text,
                "attachments": attachments,
                "kind": kind,
                "interrupt": interrupt,
                "thread_id": thread_id,
            }
        )

    async def start_typing_indicator(self, *, user_key: str) -> None:
        return None

    async def stop_typing_indicator(self, *, user_key: str) -> None:
        return None


@pytest.fixture(autouse=True)
def _isolated_registry():
    ChannelRegistry.reset()
    yield
    ChannelRegistry.reset()


def _patch_user_key(monkeypatch: pytest.MonkeyPatch, user_key: str) -> None:
    monkeypatch.setattr(
        dt, "get_config", lambda: {"configurable": {"user_key": user_key}}
    )


@pytest.mark.asyncio
async def test_send_message_resolves_channel_and_delegates_to_deliver(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    channel = _RecordingChannel(ChannelKind.TELEGRAM)
    ChannelRegistry.register(channel)
    _patch_user_key(monkeypatch, "telegram:123")

    await dt.send_message.ainvoke({"text": "oi", "attachment_paths": []})

    assert channel.calls == [
        {
            "user_key": "telegram:123",
            "text": "oi",
            "attachments": (),
            "kind": "normal",
            "interrupt": None,
            "thread_id": None,
        }
    ]


@pytest.mark.asyncio
async def test_send_message_surfaces_registry_error_when_channel_unregistered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_user_key(monkeypatch, "telegram:123")

    with pytest.raises(RuntimeError, match="telegram"):
        await dt.send_message.ainvoke({"text": "oi", "attachment_paths": []})
