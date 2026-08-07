"""Testes da tool `web_fetch` (add-web-fetch-tool REQ-001..007)."""
from __future__ import annotations

import httpx
import pytest

import src.tools.web_fetch_tool as wft
from src.tools.web_fetch_tool import web_fetch

_PUBLIC = "http://93.184.216.34/page"


def _invoke(url: str, *, transport: httpx.BaseTransport | None = None):
    if transport is not None:
        wft._TRANSPORT_OVERRIDE = transport
    try:
        return web_fetch.invoke({"url": url})
    finally:
        wft._TRANSPORT_OVERRIDE = None


def test_fetch_html_success() -> None:
    """Unit-1: HTML 200 → content textual, nome web_fetch."""
    html = "<html><body><p>Olá mundo</p><script>x()</script></body></html>"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=html.encode(),
            headers={"content-type": "text/html; charset=utf-8"},
        )

    result = _invoke(_PUBLIC, transport=httpx.MockTransport(handler))
    assert web_fetch.name == "web_fetch"
    assert "error" not in result
    assert "Olá mundo" in result["content"]
    assert "x()" not in result["content"]
    assert result["truncated"] is False


@pytest.mark.parametrize("bad", ["example.com/page", "file:///etc/passwd"])
def test_rejects_invalid_scheme_without_request(bad: str) -> None:
    """Unit-2: URL inválida → error, sem GET."""
    hits: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        hits.append(str(request.url))
        return httpx.Response(200, content=b"nope")

    result = _invoke(bad, transport=httpx.MockTransport(handler))
    assert "error" in result
    assert hits == []


def test_text_plain_ok_pdf_rejected() -> None:
    """Unit-3: text/plain ok; application/pdf → error."""

    def plain_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b"hello plain",
            headers={"content-type": "text/plain"},
        )

    ok = _invoke(_PUBLIC, transport=httpx.MockTransport(plain_handler))
    assert ok.get("content") == "hello plain"
    assert "error" not in ok

    def pdf_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b"%PDF-1.4 binary",
            headers={"content-type": "application/pdf"},
        )

    bad = _invoke(_PUBLIC, transport=httpx.MockTransport(pdf_handler))
    assert "error" in bad
    assert "%PDF" not in bad.get("content", "")
    assert "%PDF" not in bad["error"]


def test_http_404_and_timeout_become_error() -> None:
    """Unit-4: 404 e timeout → error dict."""

    def not_found(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, content=b"missing")

    r404 = _invoke(_PUBLIC, transport=httpx.MockTransport(not_found))
    assert "error" in r404
    assert "404" in r404["error"]

    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out")

    rto = _invoke(_PUBLIC, transport=httpx.MockTransport(boom))
    assert "error" in rto
    assert "timeout" in rto["error"].lower() or "timed" in rto["error"].lower()


def test_truncation_and_finite_default_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unit-5: truncamento marcado; timeout default finito."""
    monkeypatch.setattr(wft, "_MAX_CHARS", 20)

    def handler(request: httpx.Request) -> httpx.Response:
        body = ("palavra " * 20).encode()
        return httpx.Response(
            200,
            content=body,
            headers={"content-type": "text/plain"},
        )

    result = _invoke(_PUBLIC, transport=httpx.MockTransport(handler))
    assert result["truncated"] is True
    assert len(result["content"]) <= 20 + len("\n\n[...truncated...]")
    assert "[...truncated...]" in result["content"]

    assert wft._default_timeout() > 0
    assert wft._default_timeout() < float("inf")


def test_redirect_to_private_blocked() -> None:
    """Unit-6: 302 para loopback → error SSRF."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/page":
            return httpx.Response(
                302,
                headers={"location": "http://127.0.0.1:8001/secret"},
            )
        return httpx.Response(200, content=b"internal secret")

    result = _invoke(_PUBLIC, transport=httpx.MockTransport(handler))
    assert "error" in result
    assert "não permitido" in result["error"] or "SSRF" in result["error"]
    assert "internal secret" not in result.get("content", "")


def test_docstring_and_canonical_name() -> None:
    """Unit-7: docstring orienta leitura de URL; nome canônico."""
    assert web_fetch.name == "web_fetch"
    doc = (web_fetch.description or "").lower()
    assert "url" in doc
    assert "search" in doc or "busca" in doc or "pesquis" in doc
