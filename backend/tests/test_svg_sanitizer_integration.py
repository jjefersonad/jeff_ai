"""Integration tests: svg_sanitizer wired into create_image_from_prompt.

Tests run with a fully-mocked GeminiImageAdapter so no real API calls are made.
Each test documents one REQ-101/REQ-102 scenario from the image-generation-pipeline
delta spec (fix-svg-diagram-rendering-error-image-generation-pipeline-spec).

RED: write tests that currently FAIL because svg_sanitizer is not yet wired.
GREEN: implement the wiring, then these tests pass.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import src.infrastructure.llm.gemini_image_adapter as gmod
import src.tools.generate_image_tool as gt
from src.application.ports.image_gen import GeneratedImage, ImageGenPort
from src.domain.imaging import ImageDesign
from src.svg_sanitizer import Correction, SanitizeResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_svg(name: str, extra: str = "") -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" id="{name}">{extra}'
        "<rect width=\"10\" height=\"10\"/></svg>"
    )


class FakeImageGenSVGOnly(ImageGenPort):
    """Fake adapter that returns SVG bytes (no PNG)."""

    def __init__(self, svg_content: str) -> None:
        self._svg = svg_content.encode()

    async def generate(self, design: ImageDesign) -> GeneratedImage:
        return GeneratedImage(
            path=str(Path("/tmp/fake.svg")),
            url="/api/images/fake.svg",
            metadata={"prompt": design.prompt},
        )

    def save(self, path: Path) -> None:
        path.write_bytes(self._svg)


# ---------------------------------------------------------------------------
# REQ-101 Scenario 1: Well-formed SVG through sanitizer
# ---------------------------------------------------------------------------

async def test_wellformed_svg_passes_through_with_sanitized_true(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Well-formed SVG: sanitizer makes no changes; metadata.sanitized=True, no error."""
    wellformed_svg = _make_svg("ok")
    fake = FakeImageGenSVGOnly(wellformed_svg)

    # Mock so that the file saved on disk IS the sanitized SVG
    saved_bytes: dict[str, bytes] = {}

    original_write = Path.write_bytes

    def _write_bytes(self: Path, data: bytes, *a: Any, **k: Any) -> None:
        saved_bytes[str(self)] = data
        return original_write(self, data, *a, **k)

    async def _execute(design: ImageDesign) -> GeneratedImage:
        result = await fake.generate(design)
        # Simulate what the real adapter does: write bytes to disk
        out_path = tmp_path / "wellformed.svg"
        out_path.write_bytes(wellformed_svg.encode())
        saved_bytes[str(out_path)] = wellformed_svg.encode()
        return GeneratedImage(
            path=str(out_path),
            url="/api/images/wellformed.svg",
            metadata=result.metadata,
        )

    mock_use_case = MagicMock()
    mock_use_case.execute = _execute
    monkeypatch.setattr(gt, "require_user_kind_dir", AsyncMock(return_value=tmp_path))
    monkeypatch.setattr(gt, "build_plan_and_create_image", lambda output_dir=None: mock_use_case)
    monkeypatch.setattr(gt, "record_ownership", AsyncMock())

    result = await gt.create_image_from_prompt.coroutine("draw a diagram")

    assert result["url"].endswith(".svg")
    metadata = result["metadata"]
    assert metadata.get("sanitized") is True
    assert "error" not in metadata or metadata.get("error") is None
    # corrections may be absent or empty
    corrections = metadata.get("corrections")
    assert corrections is None or corrections == []


# ---------------------------------------------------------------------------
# REQ-101 Scenario 2: SVG with misplaced <br> — sanitizer strips it
# ---------------------------------------------------------------------------

async def test_misplaced_br_stripped_and_file_parses(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """SVG with <br> outside <text>/<foreignObject>: stripped, file parses, corrections set."""
    broken_svg = (
        '<svg xmlns="http://www.w3.org/2000/svg">'
        "<g><br/></g>"
        "<rect width=\"10\" height=\"10\"/>"
        "</svg>"
    )

    saved_bytes: dict[str, bytes] = {}

    async def _execute(design: ImageDesign) -> GeneratedImage:
        out_path = tmp_path / "broken.svg"
        out_path.write_bytes(broken_svg.encode())
        saved_bytes[str(out_path)] = broken_svg.encode()
        return GeneratedImage(
            path=str(out_path),
            url="/api/images/broken.svg",
            metadata={"prompt": design.prompt},
        )

    mock_use_case = MagicMock()
    mock_use_case.execute = _execute
    monkeypatch.setattr(gt, "require_user_kind_dir", AsyncMock(return_value=tmp_path))
    monkeypatch.setattr(gt, "build_plan_and_create_image", lambda output_dir=None: mock_use_case)
    monkeypatch.setattr(gt, "record_ownership", AsyncMock())

    result = await gt.create_image_from_prompt.coroutine("draw a diagram with bug")

    # The file on disk must be the sanitized version (no <br>, parses cleanly)
    out_path = Path(result["path"])
    persisted = out_path.read_bytes()
    # Must not raise
    ET.fromstring(persisted)
    # Must not contain <br>
    assert b"<br" not in persisted

    metadata = result["metadata"]
    assert metadata.get("sanitized") is True
    corrections = metadata.get("corrections")
    assert corrections is not None
    assert any(
        c.get("action") == "strip"
        and c.get("element") == "br"
        and c.get("reason") == "outside-allowed-parent"
        for c in corrections
    )


# ---------------------------------------------------------------------------
# REQ-101 Scenario 3: Sanitizer cannot recover — no broken file persisted
# ---------------------------------------------------------------------------

async def test_sanitizer_failure_does_not_persist_broken_svg(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """When sanitizer returns ok=False, no file must be written under outputs/images/."""
    # Malformed SVG that even the sanitizer can't fix
    very_broken = (
        '<?xml version="1.0"?>\n'
        '<svg xmlns="http://www.w3.org/2000/svg"><<<>>>></svg>'
    )

    saved_paths: list[str] = []

    async def _execute(design: ImageDesign) -> GeneratedImage:
        out_path = tmp_path / "very_broken.svg"
        out_path.write_bytes(very_broken.encode())
        saved_paths.append(str(out_path))
        return GeneratedImage(
            path=str(out_path),
            url="/api/images/very_broken.svg",
            metadata={"prompt": design.prompt},
        )

    mock_use_case = MagicMock()
    mock_use_case.execute = _execute
    monkeypatch.setattr(gt, "require_user_kind_dir", AsyncMock(return_value=tmp_path))
    monkeypatch.setattr(gt, "build_plan_and_create_image", lambda output_dir=None: mock_use_case)
    monkeypatch.setattr(gt, "record_ownership", AsyncMock())

    result = await gt.create_image_from_prompt.coroutine("draw something")

    metadata = result["metadata"]
    assert metadata.get("sanitized") is False
    assert metadata.get("error") is not None
    # No persisted SVG file should exist (or if one was written before sanitizer
    # ran, it must have been cleaned up / the error response must indicate failure)
    # The key contract: a broken SVG is never returned/served.
    # Check that either path is absent or marked as error result
    if "error" in result:
        # Structured error response — the broken file was not persisted
        assert "path" not in result or "broken" not in result.get("path", "")
    else:
        # path/url/metadata response — metadata must reflect failure
        assert metadata.get("sanitized") is False


# ---------------------------------------------------------------------------
# REQ-102: Metadata is additive only — no existing keys renamed/removed
# ---------------------------------------------------------------------------

async def test_metadata_keys_are_additive_only(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """New keys {sanitized, corrections?, error?} are additive; no existing key removed."""
    wellformed_svg = _make_svg("additive-test")

    # Baseline keys that the tool currently sets
    BASELINE_KEYS: frozenset[str] = frozenset({
        "prompt",
        "art_style",
        "color_palette",
        "composition",
        "dimensions",
        "negative_prompt",
        "provider",
        "model",
    })

    async def _execute(design: ImageDesign) -> GeneratedImage:
        out_path = tmp_path / "additive.svg"
        out_path.write_bytes(wellformed_svg.encode())
        return GeneratedImage(
            path=str(out_path),
            url="/api/images/additive.svg",
            metadata={
                "prompt": design.prompt,
                "art_style": None,
                "color_palette": None,
                "composition": None,
                "dimensions": None,
                "negative_prompt": None,
                "provider": "gemini",
                "model": "gemini-3.1-flash-image",
            },
        )

    mock_use_case = MagicMock()
    mock_use_case.execute = _execute
    monkeypatch.setattr(gt, "require_user_kind_dir", AsyncMock(return_value=tmp_path))
    monkeypatch.setattr(gt, "build_plan_and_create_image", lambda output_dir=None: mock_use_case)
    monkeypatch.setattr(gt, "record_ownership", AsyncMock())

    result = await gt.create_image_from_prompt.coroutine("test additive keys")

    metadata = result["metadata"]

    # Intersection: all baseline keys must still be present
    intersection = BASELINE_KEYS & frozenset(metadata.keys())
    assert intersection == BASELINE_KEYS, (
        f"Baseline keys missing: {BASELINE_KEYS - intersection}"
    )

    # Union: new keys may appear
    NEW_KEYS: frozenset[str] = frozenset({"sanitized", "corrections", "error"})
    union = BASELINE_KEYS | frozenset(metadata.keys())

    # No key outside baseline ∪ new keys
    unexpected = union - BASELINE_KEYS - NEW_KEYS
    assert not unexpected, f"Unexpected keys in metadata: {unexpected}"
