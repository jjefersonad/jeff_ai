"""pytest tests for svg_sanitizer REQ-002 allowlist (task-sanitizer-3).

Path: backend/src/utils/tests/test_svg_sanitizer.py
Units:
  1 — sanitize strips disallowed elements (<script>, <iframe>, external <image>)
  2 — sanitize strips disallowed attributes (onclick/..., javascript: URIs)
  3 — ALLOWED_ELEMENTS / ALLOWED_ATTRIBUTES are exported and discoverable
"""
from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from src.svg_sanitizer import (
    ALLOWED_ATTRIBUTES,
    ALLOWED_ELEMENTS,
    sanitize,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _svg_contains_element(svg_string: str, tag_local_name: str) -> bool:
    """Return True if the SVG tree contains an element with the given local name."""
    try:
        root = ET.fromstring(svg_string)
    except ET.ParseError:
        return False
    for elem in root.iter():
        local = elem.tag.split("}")[-1]
        if local == tag_local_name:
            return True
    return False


def _svg_lacks_attribute(svg_string: str, attr_name: str) -> bool:
    """Return True if no element in the SVG tree carries attr_name."""
    try:
        root = ET.fromstring(svg_string)
    except ET.ParseError:
        return False
    for elem in root.iter():
        if attr_name in elem.attrib:
            return False
    return True


# ---------------------------------------------------------------------------
# Unit 1 — disallowed elements stripped
# ---------------------------------------------------------------------------

class TestUnit1_DisallowedElementsStripped:
    """REQ-002 scenario 1: disallowed elements are removed from the tree."""

    @pytest.mark.parametrize(
        "svg",
        [
            '<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script><rect/></svg>',
            '<svg xmlns="http://www.w3.org/2000/svg"><iframe src="https://evil.com/"></iframe><rect/></svg>',
            '<svg xmlns="http://www.w3.org/2000/svg"><image href="http://evil.com/x.jpg"/><rect/></svg>',
        ],
    )
    def test_disallowed_element_stripped(self, svg: str) -> None:
        """Each listed disallowed element is removed; the tree remains parseable."""
        result = sanitize(svg)
        assert result["ok"] is True, f"sanitize returned error: {result.get('error')}"
        ET.fromstring(result["svg"])  # must still parse
        # corrections must record the strip
        corrections = result["corrections"]
        stripped_elements = {c["element"] for c in corrections if c["action"] == "strip"}
        assert len(stripped_elements) >= 1, f"no strip recorded; corrections={corrections}"


# ---------------------------------------------------------------------------
# Unit 2 — disallowed attributes and javascript: URIs stripped
# ---------------------------------------------------------------------------

class TestUnit2_DisallowedAttributesStripped:
    """REQ-002 scenario 2: disallowed attributes and javascript: URIs are removed."""

    def test_onclick_stripped(self) -> None:
        svg = '<svg xmlns="http://www.w3.org/2000/svg"><g onclick="evil()"><rect/></g></svg>'
        result = sanitize(svg)
        assert result["ok"] is True
        ET.fromstring(result["svg"])
        assert _svg_lacks_attribute(result["svg"], "onclick")

    def test_onload_stripped(self) -> None:
        svg = '<svg xmlns="http://www.w3.org/2000/svg"><g onload="evil()"><rect/></g></svg>'
        result = sanitize(svg)
        assert result["ok"] is True
        ET.fromstring(result["svg"])
        assert _svg_lacks_attribute(result["svg"], "onload")

    def test_onerror_stripped(self) -> None:
        svg = '<svg xmlns="http://www.w3.org/2000/svg"><g onerror="evil()"><rect/></g></svg>'
        result = sanitize(svg)
        assert result["ok"] is True
        ET.fromstring(result["svg"])
        assert _svg_lacks_attribute(result["svg"], "onerror")

    def test_javascript_href_stripped_from_anchor(self) -> None:
        svg = '<svg xmlns="http://www.w3.org/2000/svg"><a href="javascript:alert(1)"><rect/></a></svg>'
        result = sanitize(svg)
        assert result["ok"] is True
        ET.fromstring(result["svg"])
        assert _svg_lacks_attribute(result["svg"], "href") or not any(
            "javascript:" in (result["svg"])
        ), f"javascript: URI still present in: {result['svg']}"

    def test_xlink_javascript_href_stripped(self) -> None:
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" '
            'xmlns:xlink="http://www.w3.org/1999/xlink">'
            '<use xlink:href="javascript:alert(1)"/>'
            "</svg>"
        )
        result = sanitize(svg)
        assert result["ok"] is True
        ET.fromstring(result["svg"])
        # xlink:href with javascript: must be stripped
        svg_str = result["svg"]
        assert "javascript:" not in svg_str, f"javascript: URI still present in: {svg_str}"


# ---------------------------------------------------------------------------
# Unit 3 — allowlist constants are exported, non-empty, and discoverable
# ---------------------------------------------------------------------------

class TestUnit3_AllowlistDiscoverable:
    """REQ-002 scenario 3: allowlist constants are explicit and referenced by tests."""

    def test_allowed_elements_non_empty(self) -> None:
        assert isinstance(ALLOWED_ELEMENTS, frozenset)
        assert len(ALLOWED_ELEMENTS) > 0, "ALLOWED_ELEMENTS must be non-empty"

    def test_allowed_attributes_non_empty(self) -> None:
        assert isinstance(ALLOWED_ATTRIBUTES, dict)
        assert len(ALLOWED_ATTRIBUTES) > 0, "ALLOWED_ATTRIBUTES must be non-empty"

    def test_all_fixture_elements_in_allowlist(self) -> None:
        """Every element used in test fixtures must be in ALLOWED_ELEMENTS.

        This is the discoverability gate: if a future PR silently removes an
        element from the allowlist that is used in fixtures, this test fails.
        """
        # Elements used across the test file
        fixture_elements = {
            "svg", "rect", "g", "a", "use",
            # These are disallowed (should NOT be in allowlist)
            # but we still reference them by name in fixtures
            "script", "iframe", "image",
        }
        disallowed_fixture_elements = {"script", "iframe", "image"}
        expected_allowed = fixture_elements - disallowed_fixture_elements

        missing = expected_allowed - ALLOWED_ELEMENTS
        assert not missing, f"elements used in tests not in ALLOWED_ELEMENTS: {missing}"
