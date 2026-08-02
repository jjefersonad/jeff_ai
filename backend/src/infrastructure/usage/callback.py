"""Callback LangChain que persiste uso de tokens de chat ao fim do model call.

Chat models não têm `on_chat_model_end` no `BaseCallbackHandler` — a conclusão
é roteada para `on_llm_end` com um `LLMResult` contendo a `AIMessage`.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult
from langgraph.config import get_config

from src.infrastructure.usage.repository import UsageRepository
from src.infrastructure.usage.user_key import resolve_user_key


def _extract_ai_message(response: LLMResult) -> AIMessage | None:
    """Retorna a primeira AIMessage das generations, se houver."""
    for generation_list in response.generations or []:
        for generation in generation_list:
            if isinstance(generation, ChatGeneration):
                message = generation.message
                if isinstance(message, AIMessage):
                    return message
            message = getattr(generation, "message", None)
            if isinstance(message, AIMessage):
                return message
    return None


def _provider_and_model(message: AIMessage) -> tuple[str, str]:
    """Deriva provider/model do response_metadata da AIMessage."""
    meta = message.response_metadata or {}
    provider = (
        meta.get("model_provider")
        or meta.get("ls_provider")
        or "unknown"
    )
    model = (
        meta.get("model_name")
        or meta.get("model")
        or meta.get("ls_model_name")
        or "unknown"
    )
    return str(provider), str(model)


class UsageRecordingCallback(BaseCallbackHandler):
    """Grava eventos `source=chat` a partir de `usage_metadata` da AIMessage."""

    def __init__(self, repository: UsageRepository) -> None:
        """Injeta o repositório usado em cada gravação."""
        super().__init__()
        self._repository = repository

    def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        """Equivalente a on_chat_model_end: lê usage e chama repository.record."""
        del run_id, parent_run_id, kwargs  # unused; signature matches LangChain
        message = _extract_ai_message(response)
        if message is None:
            return

        usage = message.usage_metadata
        if not usage:
            return

        prompt_tokens = usage.get("input_tokens")
        completion_tokens = usage.get("output_tokens")
        total_tokens = usage.get("total_tokens")
        if (
            prompt_tokens is None
            and completion_tokens is None
            and total_tokens is None
        ):
            return

        try:
            config = get_config()
        except Exception:
            config = {}
        configurable = (config or {}).get("configurable") or {}
        # Prefer server-stamped configurable.user_key; fallback owner from
        # configurable.owner or langgraph_auth_user.identity (web session).
        auth_user = configurable.get("langgraph_auth_user") or {}
        owner = configurable.get("owner") or auth_user.get("identity")
        user_key = resolve_user_key(
            user_key=configurable.get("user_key"),
            owner=owner,
        )
        thread_id = configurable.get("thread_id")
        provider, model = _provider_and_model(message)

        self._repository.record(
            user_key=user_key,
            thread_id=thread_id,
            provider=provider,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            source="chat",
        )


__all__ = ["UsageRecordingCallback"]
