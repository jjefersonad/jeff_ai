"""`ChatAttachmentPreprocessingMiddleware` — path-first injection of turn attachments.

Design D6 / session-owned-file-access REQ-001–002: when the latest
`HumanMessage` carries `additional_kwargs.attachment_ids`, load each id with
thread + user isolation and inject `filename`, `content_type`, and
`storage_path` into a *copy* of the message for the model call. The
checkpointer keeps the original HumanMessage untouched.

Caption via `extract_and_inject` is best-effort (MAY); it MUST NOT replace
`storage_path`.
"""
from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ModelRequest
from langchain_core.messages import BaseMessage, HumanMessage

from src.infrastructure.attachments.store import StoredAttachment, load_attachments
from src.infrastructure.ownership.store import resolve_user_id
from src.tools.attachment_context import extract_and_inject

try:
    from langgraph.config import get_config
except ImportError:  # pragma: no cover

    def get_config() -> dict[str, Any]:  # type: ignore[misc]
        return {}


_log = logging.getLogger(__name__)


def _message_content_as_str(content: Any) -> str:
    if isinstance(content, str):
        return content
    return str(content)


def _path_block(attachment: StoredAttachment) -> str:
    """Bloco canônico path-first (REQ-001). Caption appended separately."""
    return (
        f"[Attachment: {attachment.filename}]\n"
        f"content_type: {attachment.content_type}\n"
        f"storage_path: {attachment.storage_path}"
    )


def _not_found_block(attachment_id: str) -> str:
    return f"[Attachment: {attachment_id} — could not be read: not found]"


def _build_injection_text(
    ids: list[str],
    loaded: list[StoredAttachment | None],
) -> str:
    parts: list[str] = []
    for attachment_id, attachment in zip(ids, loaded, strict=True):
        if attachment is None:
            parts.append(_not_found_block(attachment_id))
            continue
        block = _path_block(attachment)
        # Caption best-effort (D6): never replaces storage_path.
        try:
            caption = extract_and_inject(attachment)
        except Exception as exc:  # pragma: no cover — defensive
            _log.debug("caption skipped for %s: %s", attachment_id, exc)
            caption = ""
        if caption and caption.strip():
            # Avoid duplicating the filename header when extract_and_inject
            # already wraps with [Attachment: ...].
            caption_body = caption
            prefix = f"[Attachment: {attachment.filename}]"
            if caption_body.startswith(prefix):
                caption_body = caption_body[len(prefix) :].lstrip("\n")
            if caption_body.strip():
                block = f"{block}\n{caption_body}"
        parts.append(block)
    return "\n\n".join(parts)


def _strip_attachment_ids(kwargs: dict[str, Any]) -> dict[str, Any]:
    cleaned = dict(kwargs)
    cleaned.pop("attachment_ids", None)
    return cleaned


class ChatAttachmentPreprocessingMiddleware(AgentMiddleware[Any, Any, Any]):
    """Inject owned attachment paths into the LLM-facing HumanMessage."""

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[Any]],
    ) -> Any:
        rewritten = await self._maybe_rewrite_messages(request)
        return await handler(rewritten)

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Any],
    ) -> Any:
        """Sync path: pass-through (attachment load is async-only).

        Production runs via `astream`/`ainvoke` and always hits
        `awrap_model_call`. Sync invoke without attachments stays intact.
        """
        return handler(request)

    async def _maybe_rewrite_messages(self, request: ModelRequest) -> ModelRequest:
        messages = list(request.messages or [])
        if not messages:
            return request

        last_idx = None
        for i in range(len(messages) - 1, -1, -1):
            if isinstance(messages[i], HumanMessage):
                last_idx = i
                break
        if last_idx is None:
            return request

        last = messages[last_idx]
        assert isinstance(last, HumanMessage)
        kwargs = dict(last.additional_kwargs or {})
        raw_ids = kwargs.get("attachment_ids")
        if not isinstance(raw_ids, list) or not raw_ids:
            return request

        ids = [str(x) for x in raw_ids]
        configurable = get_config().get("configurable", {}) or {}
        thread_id = str(configurable.get("thread_id") or "")
        user_id = await resolve_user_id()
        if not thread_id or not user_id:
            # Fail-closed: cannot isolate without identity — treat as not found.
            injection = "\n\n".join(_not_found_block(i) for i in ids)
        else:
            loaded = await load_attachments(ids, thread_id=thread_id, user_id=user_id)
            injection = _build_injection_text(ids, loaded)

        original_text = _message_content_as_str(last.content)
        new_content = f"{original_text}\n\n{injection}" if original_text else injection
        new_message = HumanMessage(
            content=new_content,
            additional_kwargs=_strip_attachment_ids(kwargs),
            id=getattr(last, "id", None),
        )
        new_messages: list[BaseMessage] = list(messages)
        new_messages[last_idx] = new_message
        return request.override(messages=new_messages)


__all__ = ["ChatAttachmentPreprocessingMiddleware"]
