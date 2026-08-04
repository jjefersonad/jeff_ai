"""Testes do adapter `WhatsAppChannel` (task `unify-message-delivery-pipeline-task-adapters-2`).

Cobre REQ-005/REQ-008 (whatsapp-channel) e REQ-001/REQ-003/REQ-005
(chat-channel-port). `evolution_client.send_text`/`send_image` são
patchados diretamente (já testados isoladamente contra `respx` em
`test_evolution_client.py`) — aqui só verificamos que o adapter monta a
chamada certa e trata falha corretamente.
"""
from __future__ import annotations

import base64
import logging
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from src.domain.channels import ChannelKind, OutputAttachment
from src.infrastructure.channels.whatsapp_channel import WhatsAppChannel


def _outside_window_error() -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "http://evolution_api:8080/message/sendText/jeff-ai-central")
    response = httpx.Response(403, json={"error": {"code": 131047}}, request=request)
    return httpx.HTTPStatusError("outside window", request=request, response=response)


def test_channel_kind_is_whatsapp() -> None:
    channel = WhatsAppChannel(instance="jeff-ai-central")

    assert channel.channel_kind is ChannelKind.WHATSAPP


@pytest.mark.asyncio
async def test_deliver_text_only_calls_send_text_with_parsed_phone() -> None:
    channel = WhatsAppChannel(instance="jeff-ai-central")

    with patch(
        "src.infrastructure.channels.whatsapp_channel.evolution_client.send_text",
        new_callable=AsyncMock,
    ) as send_text_mock:
        await channel.deliver(
            user_key="whatsapp:5511999998888", text="Olá!", attachments=(), kind="normal"
        )

    send_text_mock.assert_awaited_once_with("jeff-ai-central", "5511999998888", "Olá!")


@pytest.mark.asyncio
async def test_deliver_swallows_outside_window_error_and_logs_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    channel = WhatsAppChannel(instance="jeff-ai-central")

    with (
        patch(
            "src.infrastructure.channels.whatsapp_channel.evolution_client.send_text",
            new_callable=AsyncMock,
            side_effect=_outside_window_error(),
        ),
        caplog.at_level(logging.WARNING),
    ):
        await channel.deliver(
            user_key="whatsapp:5511999998888", text="Olá!", attachments=(), kind="normal"
        )

    assert any(
        "outside_window" in record.message and record.levelno == logging.WARNING
        for record in caplog.records
    )


@pytest.mark.asyncio
async def test_deliver_long_text_is_chunked_preserving_order() -> None:
    channel = WhatsAppChannel(instance="jeff-ai-central")
    long_text = "a" * 9000

    with patch(
        "src.infrastructure.channels.whatsapp_channel.evolution_client.send_text",
        new_callable=AsyncMock,
    ) as send_text_mock:
        await channel.deliver(
            user_key="whatsapp:5511999998888", text=long_text, attachments=(), kind="normal"
        )

    assert send_text_mock.await_count == 3
    chunks = [call.args[2] for call in send_text_mock.await_args_list]
    assert all(len(chunk) <= 4096 for chunk in chunks)
    assert "".join(chunks) == long_text


@pytest.mark.asyncio
async def test_deliver_image_attachment_calls_send_image_with_base64_and_caption(tmp_path) -> None:
    image_path = tmp_path / "foo.png"
    image_path.write_bytes(b"fake-png-bytes")
    channel = WhatsAppChannel(instance="jeff-ai-central")
    attachment = OutputAttachment(path=str(image_path), mime="image/png", display_name="foo.png")

    with patch(
        "src.infrastructure.channels.whatsapp_channel.evolution_client.send_image",
        new_callable=AsyncMock,
    ) as send_image_mock:
        await channel.deliver(
            user_key="whatsapp:5511999998888",
            text="Aqui está",
            attachments=(attachment,),
            kind="normal",
        )

    send_image_mock.assert_awaited_once()
    args, kwargs = send_image_mock.await_args
    assert args[0] == "jeff-ai-central"
    assert args[1] == "5511999998888"
    assert args[2] == base64.b64encode(b"fake-png-bytes").decode()
    assert kwargs["caption"] == "Aqui está"


@pytest.mark.asyncio
async def test_deliver_interruption_sends_approval_pending_text() -> None:
    channel = WhatsAppChannel(instance="jeff-ai-central")

    with patch(
        "src.infrastructure.channels.whatsapp_channel.evolution_client.send_text",
        new_callable=AsyncMock,
    ) as send_text_mock:
        await channel.deliver(
            user_key="whatsapp:5511999998888",
            text=None,
            attachments=(),
            kind="interruption",
        )

    send_text_mock.assert_awaited_once()
    args, _ = send_text_mock.await_args
    assert args[0] == "jeff-ai-central"
    assert args[1] == "5511999998888"
    assert "aprovação" in args[2]
