"""Pure SVG sanitizer (svg-output-sanitization capability, REQ-001/002/003).

Public API:
    - sanitize(content: str) -> SanitizeResult
    - ALLOWED_ELEMENTS: frozenset[str]
    - ALLOWED_ATTRIBUTES: dict[str, frozenset[str]]
    - Correction, SanitizeResult TypedDicts (re-exported for callers)

The function is pure (no I/O, no logger, no global state) — see REQ-003.
Behaviour and acceptance criteria live in the change's spec/design artifacts:

    specs:
        fix-svg-diagram-rendering-error-svg-output-sanitization-spec
    design:
        fix-svg-diagram-rendering-error-design  (decisions D1, D2, D3, D4)
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import TypedDict


class Correction(TypedDict):
    """A single change applied during sanitization.

    `action` is one of the supported operations (currently only "strip").
    `element` is the element name (or the qualified attribute name, e.g.
    "g@onclick") that was acted on. `reason` is a short, stable, machine-
    readable string explaining why the action was taken.
    """

    action: str
    element: str
    reason: str


class SanitizeResult(TypedDict, total=False):
    """Structured result of `sanitize()`.

    Invariants:
        - `ok` is always present.
        - If `ok` is True: `svg` is present (a non-empty string), `corrections`
          is present (possibly empty), `error` is absent.
        - If `ok` is False: `error` is present (a non-empty string), `svg` is
          absent, `corrections` is absent.
    """

    ok: bool
    svg: str
    corrections: list[Correction]
    error: str


# --- Allowlist (REQ-002) ---------------------------------------------------
# Values from the design's "Allowlist" table (D2).
ALLOWED_ELEMENTS: frozenset[str] = frozenset({
    "svg", "g", "a", "path", "rect", "circle", "ellipse", "line",
    "polyline", "polygon", "text", "tspan", "defs",
    "linearGradient", "radialGradient", "stop", "use",
    "title", "desc", "style", "foreignObject",
})

# Per-element allowed attributes. Keys are element names; values are
# allowed attribute names for that element. Special keys:
#   "*" — attributes allowed on all elements.
ALLOWED_ATTRIBUTES: dict[str, frozenset[str]] = {
    "*": frozenset({
        "id", "class", "style", "xmlns",
        "fill", "stroke", "stroke-width", "stroke-linecap",
        "stroke-linejoin", "stroke-dasharray", "stroke-opacity",
        "fill-opacity", "opacity", "transform",
        "font-family", "font-size", "font-weight", "font-style",
        "text-anchor", "dominant-baseline", "letter-spacing",
        "x", "y", "x1", "y1", "x2", "y2", "cx", "cy", "r", "rx", "ry",
        "width", "height", "viewBox", "preserveAspectRatio",
        "points", "d", "pathLength",
        "offset", "stop-color", "stop-opacity",
        "gradientUnits", "gradientTransform",
        "spreadMethod", "fx", "fy", "cx", "cy", "r", "gradientTransform",
        "href", "xlink:href",
    }),
    "text": frozenset({"x", "y", "dx", "dy"}),
    "tspan": frozenset({"x", "y", "dx", "dy"}),
    "a": frozenset({"xlink:href", "href", "target"}),
    "use": frozenset({"href", "xlink:href", "x", "y", "width", "height"}),
    "image": frozenset({"href", "xlink:href", "x", "y", "width", "height"}),
}

# Elements that are allowed to contain <br> directly.
_BR_ALLOWED_PARENTS = frozenset({"text", "foreignObject", "tspan"})


def sanitize(content: str) -> SanitizeResult:
    """Sanitize an agent-produced SVG string and return a structured result.

    - REQ-001: parse with `xml.etree.ElementTree.fromstring`; strip any
      `<br>` whose parent is not `<text>`/`<foreignObject>`; return
      `{ok: True, svg, corrections}` if the result parses, otherwise
      `{ok: False, error}`.
    - REQ-002: enforce `ALLOWED_ELEMENTS` and `ALLOWED_ATTRIBUTES`; strip
      `javascript:` URIs (populated in task sanitizer-3).
    - REQ-003: pure function — no I/O, no logger, no global mutation.
    """
    corrections: list[Correction] = []

    # Register SVG namespace so ET.tostring() uses the "svg:" prefix instead
    # of "ns0:".  register_namespace is idempotent; calling it repeatedly
    # with the same prefix URI has no additional effect beyond the first call.
    ET.register_namespace("svg", "http://www.w3.org/2000/svg")

    # --- Step 1: Pre-process malformed XML (unclosed tags) ----------
    processed = _auto_close_open_tags(content)

    # --- Step 2: Parse ----------------------------------------------
    root: ET.Element
    try:
        root = ET.fromstring(processed)
    except ET.ParseError as exc:
        return _error_result(f"parse error: {exc}")

    # --- Step 3: Strip <br> outside allowed parents ---------------
    _strip_invalid_br(root, corrections)

    # --- Step 4: Strip disallowed elements --------------------------
    _strip_disallowed_elements(root, corrections)

    # --- Step 5: Strip disallowed attributes and javascript: URIs ---
    _strip_disallowed_attrs(root, corrections)

    # --- Step 6: Serialize back to XML ------------------------------
    try:
        svg_out = ET.tostring(root, encoding="unicode")
    except Exception as exc:  # pragma: no cover — shouldn't happen after parse
        return _error_result(f"serialise error: {exc}")

    return _ok_result(svg_out, corrections)


# -------------------------------------------------------------------
# Internal helpers
# -------------------------------------------------------------------

_VOID_TAGS = frozenset({
    "area", "base", "br", "col", "embed", "hr", "img",
    "input", "link", "meta", "param", "source", "track", "wbr",
})


def _auto_close_open_tags(xml: str) -> str:
    """Auto-close tags that are left open (no closing tag present).

    E.g.  ``<svg><g><rect/></svg>``  →  ``<svg><g><rect/></g></svg>``

    Scans left-to-right with an open-tag stack. When a closing tag is
    encountered whose name does NOT match the top of the stack, we inject
    missing close-tags in reverse order before processing the encountered
    close-tag.
    """
    open_stack: list[str] = []  # tag names currently open
    parts: list[str] = []
    i = 0
    n = len(xml)

    while i < n:
        if xml[i] != "<":
            # Collect character
            j = i
            while j < n and xml[j] != "<":
                j += 1
            parts.append(xml[i:j])
            i = j
            continue

        # --- comment / CDATA / processing instruction --------------------
        if xml[i:i+3] == "<!--":
            end = xml.find("-->", i + 3)
            if end == -1:
                parts.append(xml[i:])
                break
            parts.append(xml[i:end + 3])
            i = end + 3
            continue
        if xml[i:i+8] == "<![CDATA[":
            end = xml.find("]]>", i + 8)
            if end == -1:
                parts.append(xml[i:])
                break
            parts.append(xml[i:end + 3])
            i = end + 3
            continue

        # --- closing tag </...> ---------------------------------------
        if xml[i:i+2] == "</":
            end = xml.find(">", i + 2)
            if end == -1:
                parts.append(xml[i:])
                break
            tag_name = xml[i+2:end].split()[0].lower()
            # Close tags until we reach the matching open tag
            while open_stack and open_stack[-1] != tag_name:
                parts.append(f"</{open_stack.pop()}>")
            if open_stack:
                open_stack.pop()  # matching tag
            parts.append(xml[i:end+1])
            i = end + 1
            continue

        # --- opening or self-closing tag <...> -------------------------
        end = xml.find(">", i)
        if end == -1:
            parts.append(xml[i:])
            break
        tag_body = xml[i+1:end]
        self_closing = tag_body.endswith("/")
        tag_name = tag_body.split()[0].split("/")[0].lower()

        if self_closing:
            # Self-closing tag — complete in itself, do not push
            pass
        elif tag_name in _VOID_TAGS:
            # Void tag (e.g. <br>, <img>, <rect/>) — complete in itself
            pass
        else:
            open_stack.append(tag_name)
        parts.append(xml[i:end+1])
        i = end + 1
        continue

    # Close any remaining open tags
    while open_stack:
        parts.append(f"</{open_stack.pop()}>")

    return "".join(parts)


def _strip_invalid_br(element: ET.Element, corrections: list[Correction]) -> None:
    """Recursively remove any <br> whose direct parent is not an allowed container."""
    allowed = _BR_ALLOWED_PARENTS
    children = list(element)  # snapshot to avoid mutation during iteration
    for child in children:
        child_tag = child.tag.split("}")[-1].lower()
        if child_tag == "br":
            parent_tag = element.tag.split("}")[-1].lower()
            if parent_tag not in allowed:
                element.remove(child)
                corrections.append(
                    {"action": "strip", "element": "br", "reason": "outside-allowed-parent"}
                )
        else:
            _strip_invalid_br(child, corrections)


# ---------------------------------------------------------------------------
# REQ-002 allowlist enforcement
# ---------------------------------------------------------------------------

def _strip_disallowed_elements(element: ET.Element, corrections: list[Correction]) -> None:
    """Recursively strip any element whose tag is not in ALLOWED_ELEMENTS."""
    allowed = ALLOWED_ELEMENTS
    children = list(element)
    for child in children:
        child_tag = child.tag.split("}")[-1].lower()
        if child_tag not in allowed:
            element.remove(child)
            corrections.append(
                {"action": "strip", "element": child_tag, "reason": "disallowed-element"}
            )
        else:
            _strip_disallowed_elements(child, corrections)


_JAVASCRIPT_SCHEME = "javascript:"


def _strip_disallowed_attrs(element: ET.Element, corrections: list[Correction]) -> None:
    """Remove disallowed attributes and strip javascript: URIs from allowed attrs."""
    global_allowed = ALLOWED_ATTRIBUTES.get("*", frozenset())
    elem_tag = element.tag.split("}")[-1].lower()
    elem_allowed = ALLOWED_ATTRIBUTES.get(elem_tag, frozenset())
    allowed_for_this = global_allowed | elem_allowed

    to_remove_attrs: list[str] = []
    for attr_name, attr_value in element.attrib.items():
        attr_lower = attr_name.split("}")[-1].lower()

        # Check 1: attribute itself not in the allowlist
        if attr_lower not in allowed_for_this:
            to_remove_attrs.append(attr_name)
            corrections.append(
                {
                    "action": "strip",
                    "element": f"{elem_tag}@{attr_lower}",
                    "reason": "disallowed-attribute",
                }
            )
            continue

        # Check 2: javascript: URI in href / xlink:href
        if attr_lower in ("href", "xlink:href") and _JAVASCRIPT_SCHEME in attr_value.lower():
            to_remove_attrs.append(attr_name)
            corrections.append(
                {
                    "action": "strip",
                    "element": f"{elem_tag}@{attr_lower}",
                    "reason": "javascript-uri",
                }
            )

    for attr_name in to_remove_attrs:
        del element.attrib[attr_name]

    # Recurse into children
    for child in list(element):
        _strip_disallowed_attrs(child, corrections)


def _ok_result(svg: str, corrections: list[Correction]) -> SanitizeResult:
    return SanitizeResult(ok=True, svg=svg, corrections=corrections)


def _error_result(error: str) -> SanitizeResult:
    return SanitizeResult(ok=False, error=error)


__all__ = [
    "ALLOWED_ATTRIBUTES",
    "ALLOWED_ELEMENTS",
    "Correction",
    "SanitizeResult",
    "sanitize",
]
