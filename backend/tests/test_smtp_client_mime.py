"""Testes do `resolve_bodies` + `_build_mime` em `smtp_client.py`
(email-send-html-only-by-default-task-smtp-1, REQ-009).

Cobre o helper que decide o tipo MIME de cada envio conforme o par
`(body_text, body_html)`:

- `text-only`      → single-part `text/html` gerado do plain
- `html-only`      → single-part `text/html` (sem duplicação)
- `both`           → `multipart/alternative` com `text/plain` primeiro e
                     `text/html` segundo
- HTML sempre sanitizado via `nh3.clean` antes de ir pro wire
"""
from __future__ import annotations

import email
from email import message_from_bytes

import pytest

from src.infrastructure.email.smtp_client import _build_mime, resolve_bodies


def test_resolve_bodies_html_only_keeps_pair() -> None:
    """unit: `resolve_bodies(None, "<p>Hi</p>")` → `(None, "<p>Hi</p>")` sanitizado."""
    text, html = resolve_bodies(None, "<p>Hi</p>")
    assert text is None
    assert html is not None
    assert "Hi" in html
    assert "<script>" not in html


def test_resolve_bodies_plain_only_generates_p_wrapped_html() -> None:
    """unit: `resolve_bodies("Hello", None)` → `("Hello", "<p>Hello</p>")` sanitizado."""
    text, html = resolve_bodies("Hello", None)
    assert text == "Hello"
    assert html is not None
    assert "Hello" in html


def test_resolve_bodies_plain_only_html_escapes_special_chars() -> None:
    """unit: `resolve_bodies("A & B <x>", None)` → o HTML escapa `&`, `<`, `>`."""
    text, html = resolve_bodies("A & B <x>", None)
    assert text == "A & B <x>"
    assert html is not None
    assert "&amp;" in html
    assert "&lt;x&gt;" in html


def test_resolve_bodies_both_keeps_pair() -> None:
    """unit: `resolve_bodies("Hello", "<p>Hello</p>")` → par original, HTML sanitizado."""
    text, html = resolve_bodies("Hello", "<p>Hello</p>")
    assert text == "Hello"
    assert html is not None
    assert "Hello" in html


@pytest.mark.parametrize(
    "text,html",
    [
        (None, None),
        ("", ""),
        (None, ""),
        ("", None),
    ],
)
def test_resolve_bodies_raises_when_both_empty(text: str | None, html: str | None) -> None:
    """unit: ambos vazios → `ValueError("Send body required")`."""
    with pytest.raises(ValueError, match="Send body required"):
        resolve_bodies(text, html)


def test_build_mime_html_only_is_single_part_text_html() -> None:
    """unit: par html-only → single-part `text/html`, sem `multipart` no wire."""
    msg = _build_mime(None, "<p>Hi</p>")
    assert msg.get_content_type() == "text/html"
    assert not msg.is_multipart()
    payload = msg.get_payload(decode=True)
    assert payload is not None
    assert b"<p>Hi</p>" in payload
    # No text/plain part at all
    assert msg.get_content_maintype() != "multipart"
    parts = list(msg.walk())
    text_plain = [p for p in parts if p.get_content_type() == "text/plain"]
    assert text_plain == []


def test_build_mime_plain_only_is_single_part_text_html_generated() -> None:
    """unit: par plain-only → single-part `text/html` com `<p>wrap</p>`."""
    msg = _build_mime("Hello", None)
    assert msg.get_content_type() == "text/html"
    assert not msg.is_multipart()
    payload = msg.get_payload(decode=True)
    assert payload is not None
    assert b"<p>" in payload
    assert b"Hello" in payload
    assert b"</p>" in payload


def test_build_mime_both_is_multipart_alternative_plain_first_html_second() -> None:
    """unit: par both → `multipart/alternative` com plain primeiro, html segundo."""
    msg = _build_mime("Hello", "<p>Hello</p>")
    assert msg.get_content_type() == "multipart/alternative"
    parts = [p for p in msg.walk() if p.get_content_type() in ("text/plain", "text/html")]
    assert len(parts) == 2
    assert parts[0].get_content_type() == "text/plain"
    assert parts[1].get_content_type() == "text/html"
    assert parts[0].get_payload(decode=True) == b"Hello"
    assert b"<p>Hello</p>" in parts[1].get_payload(decode=True)


def test_build_mime_sanitizes_script_in_html() -> None:
    """unit: HTML com `<script>` é sanitizado antes de ir pro wire."""
    msg = _build_mime(None, "<p>Hi</p><script>alert(1)</script>")
    assert msg.get_content_type() == "text/html"
    payload = msg.get_payload(decode=True)
    assert payload is not None
    assert b"<script>" not in payload
    assert b"alert(1)" not in payload
    # O conteúdo legítimo sobrevive
    assert b"Hi" in payload


def test_build_mime_sanitizes_event_handlers_in_html() -> None:
    """unit: HTML com `onerror=` é sanitizado antes de ir pro wire."""
    msg = _build_mime(None, '<img src=x onerror=alert(1)>')
    assert msg.get_content_type() == "text/html"
    payload = msg.get_payload(decode=True)
    assert payload is not None
    assert b"onerror" not in payload
