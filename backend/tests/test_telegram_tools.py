"""Testes de `src/tools/telegram_tools.py`."""
from __future__ import annotations

from pathlib import Path

import pytest

from src.application.ports.agent_runner import InterruptInfo
from src.application.ports.chat_channel import ChatChannelPort, DeliveryKind
from src.domain.channels import ChannelKind, OutputAttachment
from src.infrastructure.channels.registry import ChannelRegistry
from src.tools import telegram_tools


class _FakeBot:
    """Substitui `telegram.Bot`: grava as chamadas sem tocar a rede."""

    def __init__(self, token: str) -> None:
        self.token = token

    async def send_message(self, chat_id: str, text: str) -> str:
        _SENT_MESSAGES.append((chat_id, text))
        return "message-sent"

    async def send_photo(
        self, chat_id: str, photo: bytes, caption: str | None = None
    ) -> str:
        _SENT_PHOTOS.append((chat_id, photo, caption))
        return "photo-sent"

    async def send_document(
        self, chat_id: str, document: bytes, filename: str, caption: str | None = None
    ) -> str:
        _SENT_DOCUMENTS.append((chat_id, document, filename, caption))
        return "document-sent"


class _RecordingTelegramChannel(ChatChannelPort):
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
        self.calls.append({"user_key": user_key, "text": text, "kind": kind})

    async def start_typing_indicator(self, *, user_key: str) -> None:
        return None

    async def stop_typing_indicator(self, *, user_key: str) -> None:
        return None


_SENT_MESSAGES: list[tuple[str, str]] = []
_SENT_PHOTOS: list[tuple[str, bytes, str | None]] = []
_SENT_DOCUMENTS: list[tuple[str, bytes, str, str | None]] = []


@pytest.fixture(autouse=True)
def _fake_bot(monkeypatch: pytest.MonkeyPatch) -> None:
    _SENT_MESSAGES.clear()
    _SENT_PHOTOS.clear()
    _SENT_DOCUMENTS.clear()
    ChannelRegistry.reset()
    monkeypatch.setattr(telegram_tools, "Bot", _FakeBot)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "dummy-token")
    monkeypatch.setenv("TELEGRAM_AUTHORIZED_CHAT_ID", "12345")
    yield
    ChannelRegistry.reset()


async def test_send_telegram_message_without_chat_id_uses_authorized_chat_id() -> None:
    channel = _RecordingTelegramChannel()
    ChannelRegistry.register(channel)

    await telegram_tools.send_telegram_message.ainvoke({"text": "oi"})

    assert channel.calls == [
        {"user_key": "telegram:12345", "text": "oi", "kind": "normal"}
    ]


async def test_send_telegram_message_with_explicit_chat_id_delegates_once() -> None:
    channel = _RecordingTelegramChannel()
    ChannelRegistry.register(channel)
    long_text = "".join(f"{i:04d}-" for i in range(1800))  # ~9000 chars

    await telegram_tools.send_telegram_message.ainvoke(
        {"text": long_text, "chat_id": "999"}
    )

    assert len(channel.calls) == 1
    assert channel.calls[0]["user_key"] == "telegram:999"
    assert channel.calls[0]["text"] == long_text


def test_resolve_allowed_output_path_rejects_path_outside_outputs_root() -> None:
    with pytest.raises(telegram_tools.TelegramPathNotAllowedError):
        telegram_tools._resolve_allowed_output_path("backend/.env")


def test_resolve_allowed_output_path_rejects_traversal_escape() -> None:
    with pytest.raises(telegram_tools.TelegramPathNotAllowedError):
        telegram_tools._resolve_allowed_output_path(
            str(telegram_tools._ALLOWED_OUTPUTS_ROOT / ".." / ".env")
        )


def test_resolve_allowed_output_path_accepts_path_inside_outputs_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(telegram_tools, "_ALLOWED_OUTPUTS_ROOT", tmp_path)
    target = tmp_path / "images" / "foo.png"
    target.parent.mkdir(parents=True)
    target.touch()

    resolved = telegram_tools._resolve_allowed_output_path(str(target))

    assert resolved == target.resolve()


async def test_send_telegram_photo_reads_file_and_sends(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(telegram_tools, "_ALLOWED_OUTPUTS_ROOT", tmp_path)
    image_path = tmp_path / "images" / "foo.png"
    image_path.parent.mkdir(parents=True)
    image_path.write_bytes(b"fake-png-bytes")

    result = await telegram_tools.send_telegram_photo.ainvoke({"path": str(image_path)})

    assert result["success"] is True
    assert len(_SENT_PHOTOS) == 1
    chat_id, photo, _caption = _SENT_PHOTOS[0]
    assert chat_id == "12345"
    assert photo == b"fake-png-bytes"


async def test_send_telegram_document_reads_file_and_sends(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(telegram_tools, "_ALLOWED_OUTPUTS_ROOT", tmp_path)
    doc_path = tmp_path / "documents" / "docx" / "report.docx"
    doc_path.parent.mkdir(parents=True)
    doc_path.write_bytes(b"fake-docx-bytes")

    result = await telegram_tools.send_telegram_document.ainvoke({"path": str(doc_path)})

    assert result["success"] is True
    assert len(_SENT_DOCUMENTS) == 1
    chat_id, document, filename, _caption = _SENT_DOCUMENTS[0]
    assert chat_id == "12345"
    assert document == b"fake-docx-bytes"
    assert filename == "report.docx"


async def test_send_telegram_photo_rejects_path_outside_outputs_root() -> None:
    result = await telegram_tools.send_telegram_photo.ainvoke({"path": "backend/.env"})

    assert result["success"] is False
    assert _SENT_PHOTOS == []


async def test_send_telegram_document_rejects_path_outside_outputs_root() -> None:
    result = await telegram_tools.send_telegram_document.ainvoke({"path": "backend/.env"})

    assert result["success"] is False
    assert _SENT_DOCUMENTS == []
