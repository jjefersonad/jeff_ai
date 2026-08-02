"""Testes de `src/infrastructure/usage/callback.py` (UsageRecordingCallback)."""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from src.infrastructure.usage.callback import UsageRecordingCallback


def _llm_result_from_message(message: AIMessage) -> LLMResult:
    return LLMResult(generations=[[ChatGeneration(message=message)]])


def test_callback_records_when_usage_metadata_present(monkeypatch: pytest.MonkeyPatch) -> None:
    """REQ-001 / REQ-003: com usage_metadata, chama record(source=chat) uma vez."""
    repo = MagicMock()
    callback = UsageRecordingCallback(repository=repo)

    monkeypatch.setattr(
        "src.infrastructure.usage.callback.get_config",
        lambda: {
            "configurable": {
                "user_key": "web:user-1",
                "thread_id": "thread-abc",
            }
        },
    )

    message = AIMessage(
        content="ok",
        usage_metadata={
            "input_tokens": 100,
            "output_tokens": 40,
            "total_tokens": 140,
        },
        response_metadata={
            "model_name": "minimax-m2.7:cloud",
            "model_provider": "ollama",
        },
    )

    # Chat model completion is routed to on_llm_end (no on_chat_model_end hook).
    callback.on_llm_end(_llm_result_from_message(message), run_id=uuid4())

    repo.record.assert_called_once()
    kwargs: dict[str, Any] = repo.record.call_args.kwargs
    assert kwargs["source"] == "chat"
    assert kwargs["user_key"] == "web:user-1"
    assert kwargs["thread_id"] == "thread-abc"
    assert kwargs["prompt_tokens"] == 100
    assert kwargs["completion_tokens"] == 40
    assert kwargs["total_tokens"] == 140
    assert kwargs["provider"] == "ollama"
    assert kwargs["model"] == "minimax-m2.7:cloud"


def test_callback_omits_when_usage_metadata_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    """REQ-005: sem usage_metadata, repository.record NÃO é chamado."""
    repo = MagicMock()
    callback = UsageRecordingCallback(repository=repo)

    monkeypatch.setattr(
        "src.infrastructure.usage.callback.get_config",
        lambda: {
            "configurable": {
                "user_key": "web:user-1",
                "thread_id": "thread-abc",
            }
        },
    )

    message = AIMessage(content="ok")  # sem usage_metadata
    callback.on_llm_end(_llm_result_from_message(message), run_id=uuid4())

    repo.record.assert_not_called()


def test_callback_resolves_web_user_key_from_auth_user_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REQ-003 fallback: sem user_key, usa langgraph_auth_user.identity → web:<id>."""
    repo = MagicMock()
    callback = UsageRecordingCallback(repository=repo)

    monkeypatch.setattr(
        "src.infrastructure.usage.callback.get_config",
        lambda: {
            "configurable": {
                "thread_id": "thread-abc",
                "langgraph_auth_user": {"identity": "user-42"},
            }
        },
    )

    message = AIMessage(
        content="ok",
        usage_metadata={
            "input_tokens": 10,
            "output_tokens": 5,
            "total_tokens": 15,
        },
        response_metadata={"model_name": "m", "model_provider": "ollama"},
    )
    callback.on_llm_end(_llm_result_from_message(message), run_id=uuid4())

    repo.record.assert_called_once()
    assert repo.record.call_args.kwargs["user_key"] == "web:user-42"


def test_callback_records_when_completion_tokens_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REQ-001: completion ausente/zero → grava sem falhar (LangChain exige int)."""
    repo = MagicMock()
    callback = UsageRecordingCallback(repository=repo)

    monkeypatch.setattr(
        "src.infrastructure.usage.callback.get_config",
        lambda: {
            "configurable": {
                "user_key": "telegram:99",
                "thread_id": "t-1",
            }
        },
    )

    message = AIMessage(
        content="ok",
        usage_metadata={
            "input_tokens": 50,
            "output_tokens": 0,
            "total_tokens": 50,
        },
        response_metadata={"model_name": "m", "model_provider": "ollama"},
    )
    callback.on_llm_end(_llm_result_from_message(message), run_id=uuid4())

    repo.record.assert_called_once()
    kwargs = repo.record.call_args.kwargs
    assert kwargs["prompt_tokens"] == 50
    assert kwargs["completion_tokens"] == 0
    assert kwargs["source"] == "chat"
