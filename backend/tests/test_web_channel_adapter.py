"""Testes do adapter `WebChannel` (task `unify-message-delivery-pipeline-task-adapters-3`).

Cobre REQ-003 (chat-channel-port): texto vira um evento SSE de texto;
attachment vira um evento SSE `{kind: "image"|"document", url, display_name}`
escolhido a partir do `mime`; `attachments=()` não emite evento de anexo.

`WebChannel` recebe um `emit` (callable assíncrono) injetado — não existe
hoje um barramento SSE único no backend (o canal web atual conversa direto
com o LangGraph Platform, ver design `unify-message-delivery-pipeline`
Context); `emit` é o ponto de integração com o que quer que sirva os
eventos ao frontend.
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.domain.channels import ChannelKind, OutputAttachment
from src.infrastructure.channels.web_channel import WebChannel


def test_channel_kind_is_web() -> None:
    channel = WebChannel(emit=AsyncMock())

    assert channel.channel_kind is ChannelKind.WEB


@pytest.mark.asyncio
async def test_deliver_text_only_emits_one_text_event() -> None:
    emit = AsyncMock()
    channel = WebChannel(emit=emit)

    await channel.deliver(user_key="web:abc", text="Olá!", attachments=(), kind="normal")

    emit.assert_awaited_once_with({"kind": "text", "text": "Olá!"})


@pytest.mark.asyncio
async def test_deliver_image_attachment_emits_image_event() -> None:
    emit = AsyncMock()
    channel = WebChannel(emit=emit)
    attachment = OutputAttachment(
        path="outputs/foo.png", mime="image/png", display_name="foo.png", url="/api/files/images/foo.png"
    )

    await channel.deliver(
        user_key="web:abc", text="Aqui está", attachments=(attachment,), kind="normal"
    )

    assert emit.await_count == 2
    text_event, attachment_event = (call.args[0] for call in emit.await_args_list)
    assert text_event == {"kind": "text", "text": "Aqui está"}
    assert attachment_event == {
        "kind": "image",
        "url": "/api/files/images/foo.png",
        "display_name": "foo.png",
    }


@pytest.mark.asyncio
async def test_deliver_document_attachment_emits_document_event() -> None:
    emit = AsyncMock()
    channel = WebChannel(emit=emit)
    attachment = OutputAttachment(
        path="outputs/foo.docx",
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        display_name="foo.docx",
        url="/api/files/docx/foo.docx",
    )

    await channel.deliver(user_key="web:abc", text=None, attachments=(attachment,), kind="normal")

    emit.assert_awaited_once_with(
        {"kind": "document", "url": "/api/files/docx/foo.docx", "display_name": "foo.docx"}
    )


@pytest.mark.asyncio
async def test_deliver_no_attachments_emits_no_attachment_event() -> None:
    emit = AsyncMock()
    channel = WebChannel(emit=emit)

    await channel.deliver(user_key="web:abc", text="só texto", attachments=(), kind="normal")

    emit.assert_awaited_once_with({"kind": "text", "text": "só texto"})
