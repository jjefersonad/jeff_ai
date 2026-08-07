"""Unit tests for public_api_origin / image_url_prefix (return-public-image-url)."""

from __future__ import annotations

import pytest

from src.composition.public_url import image_url_prefix, public_api_origin


def test_next_public_api_url_takes_precedence(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEXT_PUBLIC_API_URL", "https://api.example.com")
    monkeypatch.setenv("BASE_URL", "http://other")
    monkeypatch.setenv("FRONTEND_ORIGIN", "http://frontend")
    assert public_api_origin() == "https://api.example.com"


def test_trailing_slash_normalized_on_origin_and_image_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NEXT_PUBLIC_API_URL", "https://api.example.com/")
    monkeypatch.delenv("BASE_URL", raising=False)
    monkeypatch.delenv("FRONTEND_ORIGIN", raising=False)
    assert public_api_origin() == "https://api.example.com"
    assert image_url_prefix() == "https://api.example.com/api/images"


def test_fallback_to_base_url_when_next_public_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("NEXT_PUBLIC_API_URL", raising=False)
    monkeypatch.setenv("BASE_URL", "http://localhost:8001")
    monkeypatch.delenv("FRONTEND_ORIGIN", raising=False)
    assert public_api_origin() == "http://localhost:8001"
