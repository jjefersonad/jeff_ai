"""Testes do adapter `WhatsAppChannel` (task `unify-message-delivery-pipeline-task-adapters-2`,
revisado por `fix-whatsapp-document-delivery-task-adapters-2`).

Cobre REQ-005/REQ-008 (whatsapp-channel) e REQ-001/REQ-003/REQ-005
(chat-channel-port). `evolution_client.send_text`/`send_media` são
patchados diretamente (já testados isoladamente contra `respx` em
`test_evolution_client.py`) — aqui só verificamos que o adapter monta a
chamada certa e trata falha corretamente.

Attachments (imagem/documento) passaram a usar `evolution_client.send_media`
(endpoint unificado, `media` como URL de entrega de uso único —
`delivery_tokens.mint_delivery_token`) em vez de `send_image`/base64:
verificado ao vivo contra a instância real que `/message/sendImage` e
`/message/sendDocument` não existem (404), e que `media` em base64 retorna
500 para qualquer `mediatype` nesta instância (v2.1.1).

Typing (typing-indicator-chat-channels-task-whatsapp-adapter-1):
- `start_typing_indicator` → `send_presence(composing)` + refresh cancelável.
"""
from __future__ import annotations

import asyncio
import logging
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from src.application.ports.agent_runner import InterruptInfo
from src.domain.channels import ChannelKind, OutputAttachment
from src.infrastructure.channels.whatsapp_channel import WhatsAppChannel
from src.infrastructure.web.delivery_tokens import resolve_delivery_token
from src.infrastructure.whatsapp import approval


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
async def test_deliver_image_attachment_calls_send_media_with_delivery_url(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """fix-whatsapp-document-delivery-task-adapters-2-unit-1."""
    monkeypatch.delenv("DOCUMENT_BASE_URL", raising=False)
    monkeypatch.delenv("FRONTEND_ORIGIN", raising=False)
    image_path = tmp_path / "foo.png"
    image_path.write_bytes(b"fake-png-bytes")
    channel = WhatsAppChannel(instance="jeff-ai-central")
    attachment = OutputAttachment(path=str(image_path), mime="image/png", display_name="foo.png")

    with patch(
        "src.infrastructure.channels.whatsapp_channel.evolution_client.send_media",
        new_callable=AsyncMock,
    ) as send_media_mock:
        await channel.deliver(
            user_key="whatsapp:5511999998888",
            text="Aqui está",
            attachments=(attachment,),
            kind="normal",
        )

    send_media_mock.assert_awaited_once()
    args, kwargs = send_media_mock.await_args
    assert args[0] == "jeff-ai-central"
    assert args[1] == "5511999998888"
    media_url = args[2]
    assert media_url.startswith("http://localhost:3000/public/media-delivery/")
    assert kwargs["mediatype"] == "image"
    assert kwargs["filename"] is None
    assert kwargs["caption"] == "Aqui está"

    token = media_url.rsplit("/", 1)[-1]
    payload = resolve_delivery_token(token)
    assert payload == {"file_path": str(image_path), "filename": "foo.png", "mime": "image/png"}


@pytest.mark.parametrize(
    ("mime", "basename"),
    [
        (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "relatorio.docx",
        ),
        ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "dados.xlsx"),
        (
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            "slides.pptx",
        ),
    ],
)
@pytest.mark.asyncio
async def test_deliver_office_attachment_calls_send_media_with_filename(
    mime: str, basename: str, tmp_path
) -> None:
    """fix-whatsapp-document-delivery-task-adapters-2-unit-2."""
    doc_path = tmp_path / basename
    doc_path.write_bytes(b"fake-office-bytes")
    channel = WhatsAppChannel(instance="jeff-ai-central")
    attachment = OutputAttachment(path=str(doc_path), mime=mime, display_name=basename)

    with patch(
        "src.infrastructure.channels.whatsapp_channel.evolution_client.send_media",
        new_callable=AsyncMock,
    ) as send_media_mock:
        await channel.deliver(
            user_key="whatsapp:5511999998888",
            text="Segue o arquivo",
            attachments=(attachment,),
            kind="normal",
        )

    send_media_mock.assert_awaited_once()
    _, kwargs = send_media_mock.await_args
    assert kwargs["mediatype"] == "document"
    assert kwargs["filename"] == basename
    assert kwargs["caption"] == "Segue o arquivo"


@pytest.mark.asyncio
async def test_deliver_unrecognized_mime_falls_back_to_document(tmp_path) -> None:
    """fix-whatsapp-document-delivery-task-adapters-2-unit-3."""
    file_path = tmp_path / "misterioso.bin"
    file_path.write_bytes(b"bytes quaisquer")
    channel = WhatsAppChannel(instance="jeff-ai-central")
    attachment = OutputAttachment(
        path=str(file_path), mime="application/octet-stream", display_name="misterioso.bin"
    )

    with patch(
        "src.infrastructure.channels.whatsapp_channel.evolution_client.send_media",
        new_callable=AsyncMock,
    ) as send_media_mock:
        await channel.deliver(
            user_key="whatsapp:5511999998888",
            text=None,
            attachments=(attachment,),
            kind="normal",
        )

    _, kwargs = send_media_mock.await_args
    assert kwargs["mediatype"] == "document"
    assert kwargs["filename"] == "misterioso.bin"


@pytest.mark.asyncio
async def test_deliver_attachment_swallows_missing_file_and_logs_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """fix-whatsapp-document-delivery-task-adapters-2-unit-4."""
    channel = WhatsAppChannel(instance="jeff-ai-central")
    attachment = OutputAttachment(
        path="/nonexistent/foo.png", mime="image/png", display_name="foo.png"
    )

    with caplog.at_level(logging.WARNING):
        await channel.deliver(
            user_key="whatsapp:5511999998888",
            text="Aqui está",
            attachments=(attachment,),
            kind="normal",
        )

    assert any(
        "error_kind=unexpected" in record.message and record.levelno == logging.WARNING
        for record in caplog.records
    )


@pytest.mark.asyncio
async def test_deliver_attachment_swallows_network_error_and_logs_warning(
    caplog: pytest.LogCaptureFixture, tmp_path
) -> None:
    """fix-whatsapp-document-delivery-task-adapters-2-unit-4."""
    image_path = tmp_path / "foo.png"
    image_path.write_bytes(b"fake-png-bytes")
    channel = WhatsAppChannel(instance="jeff-ai-central")
    attachment = OutputAttachment(path=str(image_path), mime="image/png", display_name="foo.png")

    with (
        patch(
            "src.infrastructure.channels.whatsapp_channel.evolution_client.send_media",
            new_callable=AsyncMock,
            side_effect=httpx.ConnectError("connection refused"),
        ),
        caplog.at_level(logging.WARNING),
    ):
        await channel.deliver(
            user_key="whatsapp:5511999998888",
            text="Aqui está",
            attachments=(attachment,),
            kind="normal",
        )

    assert any(
        "error_kind=unexpected" in record.message and record.levelno == logging.WARNING
        for record in caplog.records
    )


def _make_interrupt() -> InterruptInfo:
    return InterruptInfo(
        action_requests=({"name": "edit_file", "description": "edit_file em app.py"},),
        review_configs=({"allowed_decisions": ["approve", "reject"]},),
    )


@pytest.mark.asyncio
async def test_deliver_interruption_sends_buttons_and_registers_pending_approval() -> None:
    """task-delivery-2a-unit-1 (REQ-008 cenário 1)."""
    channel = WhatsAppChannel(instance="jeff-ai-central")
    interrupt = _make_interrupt()
    approval.clear_pending_approval("5511999998888")

    with patch(
        "src.infrastructure.channels.whatsapp_channel.evolution_client.send_buttons",
        new_callable=AsyncMock,
    ) as send_buttons_mock:
        await channel.deliver(
            user_key="whatsapp:5511999998888",
            text=None,
            attachments=(),
            kind="interruption",
            interrupt=interrupt,
            thread_id="thread-abc",
        )

    send_buttons_mock.assert_awaited_once()
    args, kwargs = send_buttons_mock.await_args
    assert args[0] == "jeff-ai-central"
    assert args[1] == "5511999998888"
    buttons = kwargs["buttons"]
    labels = [b["text"] for b in buttons]
    assert labels == ["Aprovar", "Rejeitar", "Ajustar"]

    pending = approval.get_pending_approval("5511999998888")
    assert pending is not None
    assert pending.thread_id == "thread-abc"
    assert pending.action_requests == interrupt.action_requests
    assert pending.review_configs == interrupt.review_configs
    assert pending.awaiting_edit_text is False
    approval.clear_pending_approval("5511999998888")


@pytest.mark.asyncio
async def test_deliver_interruption_falls_back_to_text_menu_on_explicit_buttons_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """task-delivery-2a-unit-2 / task-delivery-2b-unit-1 (REQ-008 cenário 2)."""
    channel = WhatsAppChannel(instance="jeff-ai-central")
    interrupt = _make_interrupt()
    approval.clear_pending_approval("5511999998888")

    with (
        patch(
            "src.infrastructure.channels.whatsapp_channel.evolution_client.send_buttons",
            new_callable=AsyncMock,
            side_effect=RuntimeError("payload not supported"),
        ),
        patch(
            "src.infrastructure.channels.whatsapp_channel.evolution_client.send_text",
            new_callable=AsyncMock,
        ) as send_text_mock,
        caplog.at_level(logging.WARNING),
    ):
        await channel.deliver(
            user_key="whatsapp:5511999998888",
            text=None,
            attachments=(),
            kind="interruption",
            interrupt=interrupt,
            thread_id="thread-abc",
        )

    assert any(
        "error_kind=unsupported_interactive" in record.message
        for record in caplog.records
    )
    send_text_mock.assert_awaited_once()
    args, _ = send_text_mock.await_args
    menu_text = args[2]
    assert "1" in menu_text and "2" in menu_text and "3" in menu_text
    assert "Aprovar" in menu_text and "Rejeitar" in menu_text and "Ajustar" in menu_text

    pending = approval.get_pending_approval("5511999998888")
    assert pending is not None
    assert pending.thread_id == "thread-abc"
    approval.clear_pending_approval("5511999998888")


# ---------------------------------------------------------------------------
# typing-indicator-chat-channels-task-whatsapp-adapter-1
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_typing_indicator_calls_send_presence_composing() -> None:
    """Unit-1: start envia presence composing (REQ-001)."""
    channel = WhatsAppChannel(instance="jeff-ai-central")

    with patch(
        "src.infrastructure.channels.whatsapp_channel.evolution_client.send_presence",
        new_callable=AsyncMock,
    ) as send_presence_mock:
        await channel.start_typing_indicator(user_key="whatsapp:5511999999999")
        try:
            send_presence_mock.assert_awaited()
            args, kwargs = send_presence_mock.await_args
            assert args[:2] == ("jeff-ai-central", "5511999999999")
            assert kwargs["presence"] == "composing"
        finally:
            await channel.stop_typing_indicator(user_key="whatsapp:5511999999999")


@pytest.mark.asyncio
async def test_start_typing_invalid_user_key_does_not_raise(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Unit-2a: user_key inválido não propaga (REQ-001)."""
    channel = WhatsAppChannel(instance="jeff-ai-central")

    with (
        patch(
            "src.infrastructure.channels.whatsapp_channel.evolution_client.send_presence",
            new_callable=AsyncMock,
        ) as send_presence_mock,
        caplog.at_level(logging.WARNING),
    ):
        result = await channel.start_typing_indicator(user_key="telegram:123")

    assert result is None
    send_presence_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_start_typing_swallows_http_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Unit-2b: falha HTTP da Evolution não propaga (REQ-002)."""
    channel = WhatsAppChannel(instance="jeff-ai-central")
    request = httpx.Request("POST", "http://evolution_api:8080/chat/sendPresence/x")
    response = httpx.Response(500, request=request)
    http_error = httpx.HTTPStatusError("boom", request=request, response=response)

    with (
        patch(
            "src.infrastructure.channels.whatsapp_channel.evolution_client.send_presence",
            new_callable=AsyncMock,
            side_effect=http_error,
        ),
        caplog.at_level(logging.WARNING),
    ):
        result = await channel.start_typing_indicator(user_key="whatsapp:5511999999999")

    assert result is None
    await channel.stop_typing_indicator(user_key="whatsapp:5511999999999")


@pytest.mark.asyncio
async def test_stop_typing_cancels_refresh_without_paused_and_second_start_replaces() -> None:
    """Unit-3: stop cancela refresh sem paused; segundo start substitui (REQ-002 / REQ-ADD-001)."""
    channel = WhatsAppChannel(instance="jeff-ai-central")

    with (
        patch(
            "src.infrastructure.channels.whatsapp_channel.evolution_client.send_presence",
            new_callable=AsyncMock,
        ) as send_presence_mock,
        patch(
            "src.infrastructure.channels.whatsapp_channel._TYPING_REFRESH_SECONDS",
            0.05,
        ),
    ):
        await channel.start_typing_indicator(user_key="whatsapp:5511999999999")
        first_task = channel._typing_tasks["whatsapp:5511999999999"]
        assert not first_task.done()

        await channel.start_typing_indicator(user_key="whatsapp:5511999999999")
        second_task = channel._typing_tasks["whatsapp:5511999999999"]
        assert first_task is not second_task
        assert first_task.cancelled() or first_task.done()

        await channel.stop_typing_indicator(user_key="whatsapp:5511999999999")
        assert "whatsapp:5511999999999" not in channel._typing_tasks
        assert second_task.cancelled() or second_task.done()

        await channel.stop_typing_indicator(user_key="whatsapp:5511999999999")

        # Nenhuma chamada com presence paused
        for call in send_presence_mock.await_args_list:
            presence = call.kwargs.get("presence")
            if presence is None and len(call.args) > 2:
                presence = call.args[2]
            assert presence != "paused"

    await asyncio.sleep(0)
