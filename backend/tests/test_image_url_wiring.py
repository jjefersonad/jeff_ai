"""Wiring de url absoluta em build_plan_and_create_image (return-public-image-url)."""
from __future__ import annotations

import base64
from unittest.mock import MagicMock

import pytest

import src.composition.dependencies as dep
import src.infrastructure.llm.gemini_image_adapter as gmod
from src.domain.imaging import ImageDesign

_PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M8AAAMBAQDJ/pLvAAAAAElFTkSuQmCC"
)


def test_build_plan_and_create_image_injects_absolute_url_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NEXT_PUBLIC_API_URL", "https://api.example.com")
    monkeypatch.delenv("BASE_URL", raising=False)
    monkeypatch.delenv("FRONTEND_ORIGIN", raising=False)
    monkeypatch.delenv("POSTGRES_URI", raising=False)

    captured: dict = {}

    class CapturingAdapter:
        def __init__(self, *args, **kwargs) -> None:
            captured["kwargs"] = kwargs

    monkeypatch.setattr(dep, "GeminiImageAdapter", CapturingAdapter)
    monkeypatch.setattr(dep, "StoreStyleRepository", lambda _store: MagicMock())
    monkeypatch.setattr(dep, "get_store", lambda: MagicMock())

    dep.build_plan_and_create_image()

    assert captured["kwargs"]["url_prefix"] == "https://api.example.com/api/images"


async def test_adapter_generate_returns_absolute_image_url(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    part = MagicMock()
    part.inline_data = object()
    image = MagicMock()
    image.save.side_effect = lambda p: open(p, "wb").write(_PNG_1X1)
    part.as_image.return_value = image
    response = MagicMock()
    response.parts = [part]
    response.usage_metadata = None
    client = MagicMock()
    client.models.generate_content.return_value = response

    monkeypatch.setattr(gmod.genai, "Client", lambda *a, **k: client)

    adapter = gmod.GeminiImageAdapter(
        output_dir=tmp_path,
        url_prefix="https://api.example.com/api/images",
    )
    monkeypatch.setattr(adapter, "_timestamp", lambda: "20260807034717")
    result = await adapter.generate(ImageDesign(prompt="gato"))

    assert result.url == "https://api.example.com/api/images/20260807034717.png"
