"""Testes de `src/infrastructure/telegram/bot_client.py` (classificação de erro)."""
from __future__ import annotations

import pytest
from telegram.error import BadRequest, Forbidden, RetryAfter, TimedOut

from src.infrastructure.telegram import bot_client


def test_classify_telegram_error_rate_limited() -> None:
    result = bot_client.classify_telegram_error(RetryAfter(30))

    assert result["success"] is False
    assert result["error_kind"] == "rate_limited"
    assert result["retryable"] is True
    assert result["retry_after"] == 30


def test_classify_telegram_error_bad_format_file_too_large() -> None:
    result = bot_client.classify_telegram_error(
        BadRequest("Request Entity Too Large")
    )

    assert result["success"] is False
    assert result["error_kind"] == "bad_format"
    assert result["retryable"] is False


def test_classify_telegram_error_forbidden() -> None:
    result = bot_client.classify_telegram_error(Forbidden("Forbidden: bot was blocked by the user"))

    assert result["success"] is False
    assert result["error_kind"] == "forbidden"
    assert result["retryable"] is False


def test_classify_telegram_error_timed_out_is_transient_and_retryable() -> None:
    result = bot_client.classify_telegram_error(TimedOut())

    assert result["success"] is False
    assert result["error_kind"] == "transient"
    assert result["retryable"] is True


@pytest.mark.asyncio
async def test_call_bot_api_never_raises_and_wraps_success() -> None:
    async def ok() -> str:
        return "message-id-123"

    result = await bot_client.call_bot_api(ok)

    assert result == {"success": True, "result": "message-id-123"}


@pytest.mark.asyncio
async def test_call_bot_api_never_raises_on_telegram_error() -> None:
    async def boom() -> None:
        raise RetryAfter(5)

    result = await bot_client.call_bot_api(boom)

    assert result["success"] is False
    assert result["error_kind"] == "rate_limited"
    assert result["retry_after"] == 5
