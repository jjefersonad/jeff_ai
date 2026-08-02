"""Testes de ownership em `create_image_from_prompt` (media-ownership-authorization REQ-001)."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

import src.tools.generate_image_tool as gt
from src.application.ports.image_gen import GeneratedImage


class _FakeUseCase:
    def __init__(self, result: GeneratedImage) -> None:
        self._result = result

    async def execute(self, design: object) -> GeneratedImage:
        return self._result


async def test_records_ownership_with_kind_image_and_basename(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = GeneratedImage(
        path="/app/backend/outputs/images/20260708120000.png",
        url="/api/images/20260708120000.png",
        metadata={"prompt": "um gato"},
    )
    monkeypatch.setattr(gt, "build_plan_and_create_image", lambda: _FakeUseCase(result))
    record = AsyncMock()
    monkeypatch.setattr(gt, "record_ownership", record)

    out = await gt.create_image_from_prompt.coroutine("um gato")

    assert out == {"path": result.path, "url": result.url, "metadata": result.metadata}
    record.assert_awaited_once_with(kind="image", filename="20260708120000.png")


async def test_ownership_failure_is_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    result = GeneratedImage(
        path="/app/backend/outputs/images/20260708120000.png",
        url="/api/images/20260708120000.png",
        metadata={"prompt": "um gato"},
    )
    monkeypatch.setattr(gt, "build_plan_and_create_image", lambda: _FakeUseCase(result))
    monkeypatch.setattr(
        gt, "record_ownership", AsyncMock(side_effect=RuntimeError("db down"))
    )

    out = await gt.create_image_from_prompt.coroutine("um gato")

    assert "error" in out
    assert "path" not in out
