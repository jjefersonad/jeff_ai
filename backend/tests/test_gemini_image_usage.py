"""Testes de gravação de usage no GeminiImageAdapter (recording REQ-001/REQ-005)."""
from __future__ import annotations

import base64
from typing import Any
from unittest.mock import MagicMock

import pytest

import src.infrastructure.llm.gemini_image_adapter as gmod
from src.domain.imaging import ImageDesign

# PNG 1x1 válido — mesmo fixture do test_gemini_image_adapter.
_PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M8AAAMBAQDJ/pLvAAAAAElFTkSuQmCC"
)


def _fake_client_with_usage(usage_metadata: Any) -> MagicMock:
    part = MagicMock()
    part.inline_data = object()
    image = MagicMock()
    image.save.side_effect = lambda p: open(p, "wb").write(_PNG_1X1)
    part.as_image.return_value = image
    response = MagicMock()
    response.parts = [part]
    response.usage_metadata = usage_metadata
    client = MagicMock()
    client.models.generate_content.return_value = response
    return client


@pytest.fixture
def repo() -> MagicMock:
    return MagicMock()


async def test_adapter_records_image_usage_when_present(
    monkeypatch: pytest.MonkeyPatch, tmp_path, repo: MagicMock
) -> None:
    """Unit-1 / REQ-001: com usage_metadata, record(source=image) com contagens do SDK."""
    usage = MagicMock()
    usage.prompt_token_count = 120
    usage.candidates_token_count = 80
    usage.total_token_count = 200

    monkeypatch.setattr(
        gmod.genai, "Client", lambda *a, **k: _fake_client_with_usage(usage)
    )
    monkeypatch.setattr(
        "src.infrastructure.llm.gemini_image_adapter.get_config",
        lambda: {
            "configurable": {
                "user_key": "web:user-1",
                "thread_id": "thread-img-1",
            }
        },
    )

    adapter = gmod.GeminiImageAdapter(output_dir=tmp_path, usage_repository=repo)
    result = await adapter.generate(ImageDesign(prompt="gato astronauta"))

    assert result.url.endswith(".png")
    repo.record.assert_called_once()
    kwargs = repo.record.call_args.kwargs
    assert kwargs["source"] == "image"
    assert kwargs["user_key"] == "web:user-1"
    assert kwargs["thread_id"] == "thread-img-1"
    assert kwargs["provider"] == "gemini"
    assert kwargs["model"] == adapter._model
    assert kwargs["prompt_tokens"] == 120
    assert kwargs["completion_tokens"] == 80
    assert kwargs["total_tokens"] == 200


async def test_adapter_omits_record_when_usage_absent(
    monkeypatch: pytest.MonkeyPatch, tmp_path, repo: MagicMock
) -> None:
    """Unit-2 / REQ-005: sem usage_metadata, record NÃO é chamado; GeneratedImage retorna."""
    monkeypatch.setattr(
        gmod.genai, "Client", lambda *a, **k: _fake_client_with_usage(None)
    )
    monkeypatch.setattr(
        "src.infrastructure.llm.gemini_image_adapter.get_config",
        lambda: {
            "configurable": {
                "user_key": "web:user-1",
                "thread_id": "thread-img-2",
            }
        },
    )

    adapter = gmod.GeminiImageAdapter(output_dir=tmp_path, usage_repository=repo)
    result = await adapter.generate(ImageDesign(prompt="paisagem"))

    assert result.url.endswith(".png")
    repo.record.assert_not_called()
