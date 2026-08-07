"""Testes de `validate_public_http_url` (add-web-fetch-tool REQ-002 / REQ-006)."""
from __future__ import annotations

import pytest

from src.infrastructure.web.url_safety import UnsafeUrlError, validate_public_http_url


def test_rejects_file_scheme() -> None:
    """Unit-1: file:// é rejeitado sem depender de HTTP."""
    with pytest.raises(UnsafeUrlError, match="não permitido|esquema|scheme"):
        validate_public_http_url("file:///etc/passwd")


@pytest.mark.parametrize(
    "bad_url",
    ["http://127.0.0.1/", "http://localhost/", "http://[::1]/"],
)
def test_rejects_localhost_loopback(bad_url: str) -> None:
    """Unit-2: loopback/localhost são rejeitados."""
    with pytest.raises(UnsafeUrlError, match="não permitido|SSRF"):
        validate_public_http_url(bad_url, resolve=lambda _host: ["127.0.0.1"])


def test_rejects_private_ip_via_dns_mock() -> None:
    """Unit-3: host que resolve para RFC1918 é rejeitado."""
    with pytest.raises(UnsafeUrlError, match="não permitido|SSRF"):
        validate_public_http_url(
            "https://evil.example/path",
            resolve=lambda _host: ["10.0.0.5"],
        )


def test_accepts_public_https_literal() -> None:
    """Sanity: IP público literal passa sem DNS."""
    validate_public_http_url("https://93.184.216.34/page")
