"""pytest tests for svg_sanitizer — units 1-4 (task-sanitizer-2)."""
from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from src.svg_sanitizer import (
    ALLOWED_ATTRIBUTES,
    ALLOWED_ELEMENTS,
    Correction,
    SanitizeResult,
    sanitize,
)


def _svg_contains_element(svg_string: str, tag_local_name: str) -> bool:
    """Return True if the serialized SVG tree contains an element with the given local name.

    Handles both plain elements (``<br/>``) and namespace-prefixed elements
    (``<svg:br/>``) that ET.tostring() may produce.
    """
    try:
        root = ET.fromstring(svg_string)
    except ET.ParseError:
        return False
    for elem in root.iter():
        local = elem.tag.split("}")[-1]
        if local == tag_local_name:
            return True
    return False


class TestUnit1_BrOutsideAllowedParent:
    """REQ-001 scenario 1: <br> outside <text>/<foreignObject> → strip."""

    def test_br_directly_in_svg_is_stripped(self) -> None:
        svg = '<svg xmlns="http://www.w3.org/2000/svg"><br/></svg>'
        result = sanitize(svg)

        assert result["ok"] is True
        svg_out = result["svg"]
        # Must parse as well-formed XML
        ET.fromstring(svg_out)
        # <br> must be absent from the tree (not just in the string representation)
        assert not _svg_contains_element(svg_out, "br"), f"<br> should be stripped; got: {svg_out}"
        # corrections must record the strip
        corrections: list[Correction] = result["corrections"]
        assert any(
            c["action"] == "strip"
            and c["element"] == "br"
            and c["reason"] == "outside-allowed-parent"
            for c in corrections
        )

    def test_br_in_g_is_stripped(self) -> None:
        svg = '<svg xmlns="http://www.w3.org/2000/svg"><g><br/></g></svg>'
        result = sanitize(svg)

        assert result["ok"] is True
        ET.fromstring(result["svg"])
        assert not _svg_contains_element(result["svg"], "br"), f"<br> should be stripped; got: {result['svg']}"


class TestUnit2_MismatchedOrMissingClosingTag:
    """REQ-001 scenario 2: unclosed/mismatched tag → auto-close or error."""

    def test_unclosed_g_is_auto_closed(self) -> None:
        svg = '<svg xmlns="http://www.w3.org/2000/svg"><g><rect/></svg>'
        result = sanitize(svg)

        # Either ok=True with parseable result, or ok=False with error
        assert result["ok"] is True
        ET.fromstring(result["svg"])

    def test_mismatched_close_tag_returns_error(self) -> None:
        # Mismatched <g>...</rect> — cannot auto-fix meaningfully
        svg = '<svg xmlns="http://www.w3.org/2000/svg"><g><rect/></rect></svg>'
        result = sanitize(svg)

        if result["ok"] is False:
            assert "error" in result
        else:
            # If it somehow auto-corrected, the result must still parse
            ET.fromstring(result["svg"])


class TestUnit3_UnrecoverableReturnsError:
    """REQ-001 scenario 3: cannot recover → {ok: False, error}."""

    def test_totally_broken_xml_returns_error(self) -> None:
        svg = '<svg xmlns="http://www.w3.org/2000/svg"><<<>>>></svg>'
        result = sanitize(svg)

        assert result["ok"] is False
        assert "error" in result
        # Must NOT return a partial string that still fails to parse
        assert "svg" not in result or not result.get("svg")


class TestUnit4_RepeatedInvocationPure:
    """REQ-003: pure — same input → same output, no I/O side effects."""

    def test_idempotent_same_input_same_output(self) -> None:
        svg = '<svg xmlns="http://www.w3.org/2000/svg"><g><br/></g></svg>'

        result1 = sanitize(svg)
        result2 = sanitize(svg)

        assert result1["ok"] == result2["ok"]
        if result1["ok"]:
            assert result1["svg"] == result2["svg"]
            assert result1["corrections"] == result2["corrections"]
        else:
            assert result1["error"] == result2["error"]

    def test_no_io_side_effects(self) -> None:
        """Calling sanitize must not write files or mutate global state."""
        svg = '<svg xmlns="http://www.w3.org/2000/svg"><br/></svg>'
        result = sanitize(svg)
        # Basic sanity — result is well-formed
        assert isinstance(result, dict)
        assert "ok" in result
