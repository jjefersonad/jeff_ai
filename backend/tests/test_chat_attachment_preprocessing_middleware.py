"""ChatAttachmentPreprocessingMiddleware — attach-1 unit-2 (REQ-001 / D6)."""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from langchain.agents.middleware.types import ModelRequest
from langchain_core.messages import HumanMessage, SystemMessage

from src.agents.unified.chat_attachment_preprocessing_middleware import (
    ChatAttachmentPreprocessingMiddleware,
)
from src.infrastructure.attachments.store import StoredAttachment


def _human(*, content: str, attachment_ids: list[str] | None = None) -> HumanMessage:
    kwargs: dict[str, Any] = {}
    if attachment_ids is not None:
        kwargs["additional_kwargs"] = {"attachment_ids": attachment_ids}
    return HumanMessage(content=content, **kwargs)


def _model_request(messages: list[Any]) -> ModelRequest:
    return ModelRequest(
        model=None,  # type: ignore[arg-type]
        messages=messages,
        system_message=SystemMessage(content="sys"),
        tools=[],
    )


def _stored(
    attachment_id: str = "att-1",
    *,
    filename: str = "logo.png",
    content_type: str = "image/png",
    storage_path: str = "/files/user-a/attachment/att-1.png",
) -> StoredAttachment:
    return StoredAttachment(
        attachment_id=attachment_id,
        thread_id="thread-1",
        filename=filename,
        content_type=content_type,
        size_bytes=10,
        storage_path=storage_path,
    )


@pytest.mark.asyncio
async def test_middleware_injects_storage_path_and_strips_attachment_ids() -> None:
    """WHEN HumanMessage has attachment_ids THEN LLM content includes storage_path
    under files/<user_id>/attachment/ and kwargs no longer contain attachment_ids.
    """
    original = _human(content="use this logo", attachment_ids=["att-1"])
    request = _model_request([original])
    mw = ChatAttachmentPreprocessingMiddleware()
    captured: list[ModelRequest] = []

    async def handler(req: ModelRequest) -> str:
        captured.append(req)
        return "ok"

    with (
        patch(
            "src.agents.unified.chat_attachment_preprocessing_middleware.resolve_user_id",
            new=AsyncMock(return_value="user-a"),
        ),
        patch(
            "src.agents.unified.chat_attachment_preprocessing_middleware.get_config",
            return_value={"configurable": {"thread_id": "thread-1", "user_key": "web:user-a"}},
        ),
        patch(
            "src.agents.unified.chat_attachment_preprocessing_middleware.load_attachments",
            new=AsyncMock(return_value=[_stored()]),
        ),
        patch(
            "src.agents.unified.chat_attachment_preprocessing_middleware.extract_and_inject",
            return_value="[Attachment: logo.png]\ncaption text",
        ),
    ):
        await mw.awrap_model_call(request, handler)

    assert captured
    messages = captured[0].messages
    assert len(messages) == 1
    llm_msg = messages[0]
    assert isinstance(llm_msg, HumanMessage)
    content = str(llm_msg.content)
    assert "/files/user-a/attachment/att-1.png" in content
    assert "logo.png" in content
    assert "image/png" in content
    # Caption best-effort may appear but must not replace path.
    assert "storage_path" in content.lower() or "/files/user-a/attachment/" in content
    assert "attachment_ids" not in (llm_msg.additional_kwargs or {})
    # Original checkpointer message untouched.
    assert original.additional_kwargs.get("attachment_ids") == ["att-1"]
    assert original.content == "use this logo"


@pytest.mark.asyncio
async def test_middleware_empty_attachment_ids_is_passthrough() -> None:
    """WHEN attachment_ids absent or empty THEN pass-through without load_attachments."""
    mw = ChatAttachmentPreprocessingMiddleware()

    for human in (
        _human(content="hello"),
        _human(content="hello", attachment_ids=[]),
    ):
        captured: list[ModelRequest] = []

        async def handler(req: ModelRequest) -> str:
            captured.append(req)
            return "ok"

        load_mock = AsyncMock()
        with (
            patch(
                "src.agents.unified.chat_attachment_preprocessing_middleware.resolve_user_id",
                new=AsyncMock(return_value="user-a"),
            ),
            patch(
                "src.agents.unified.chat_attachment_preprocessing_middleware.get_config",
                return_value={"configurable": {"thread_id": "thread-1"}},
            ),
            patch(
                "src.agents.unified.chat_attachment_preprocessing_middleware.load_attachments",
                new=load_mock,
            ),
        ):
            await mw.awrap_model_call(_model_request([human]), handler)

        assert captured
        assert captured[0].messages[0] is human or captured[0].messages[0].content == human.content
        load_mock.assert_not_called()


@pytest.mark.asyncio
async def test_middleware_not_found_block_without_path_leak() -> None:
    """WHEN load returns None THEN inject not-found block without storage_path of others."""
    original = _human(content="attach", attachment_ids=["att-spoof"])
    mw = ChatAttachmentPreprocessingMiddleware()
    captured: list[ModelRequest] = []

    async def handler(req: ModelRequest) -> str:
        captured.append(req)
        return "ok"

    with (
        patch(
            "src.agents.unified.chat_attachment_preprocessing_middleware.resolve_user_id",
            new=AsyncMock(return_value="user-a"),
        ),
        patch(
            "src.agents.unified.chat_attachment_preprocessing_middleware.get_config",
            return_value={"configurable": {"thread_id": "thread-1"}},
        ),
        patch(
            "src.agents.unified.chat_attachment_preprocessing_middleware.load_attachments",
            new=AsyncMock(return_value=[None]),
        ),
    ):
        await mw.awrap_model_call(_model_request([original]), handler)

    content = str(captured[0].messages[0].content)
    assert "could not be read: not found" in content
    assert "att-spoof" in content
    assert "/files/" not in content
