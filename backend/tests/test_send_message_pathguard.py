"""pathguard-2 — send_message attachment_paths ownership (media REQ-004)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from src.application.ports.agent_runner import InterruptInfo
from src.application.ports.chat_channel import ChatChannelPort, DeliveryKind
from src.domain.channels import ChannelKind, OutputAttachment
from src.infrastructure.channels.registry import ChannelRegistry
from src.infrastructure.ownership.path_guard import PathNotAuthorizedError
from src.tools import delivery_tools as dt


class _RecordingChannel(ChatChannelPort):
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


@pytest.mark.asyncio
async def test_send_message_refuses_path_owned_by_other_user(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """WHEN role=user send_message(attachment_paths=[other's path]) THEN refuses
    before deliver/reading bytes."""
    channel = _RecordingChannel()
    ChannelRegistry.register(channel)
    monkeypatch.setattr(
        dt,
        "get_config",
        lambda: {
            "configurable": {
                "user_key": "telegram:123",
                "role": "user",
                "thread_id": "t1",
            }
        },
    )

    other_path = str(tmp_path / "user-b" / "docs" / "secret.pdf")
    Path(other_path).parent.mkdir(parents=True)
    Path(other_path).write_bytes(b"%PDF-secret")

    async def _deny(_paths):
        raise PathNotAuthorizedError(f"path not authorized: {other_path}")

    monkeypatch.setattr(dt, "authorize_tool_paths", AsyncMock(side_effect=_deny))

    with pytest.raises(PathNotAuthorizedError):
        await dt.send_message.ainvoke(
            {"text": "here", "attachment_paths": [other_path]}
        )

    assert channel.calls == []
