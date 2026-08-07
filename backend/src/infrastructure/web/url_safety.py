"""Validação de URLs HTTP(S) públicas (anti-SSRF).

Usado por `web_fetch` e potencialmente por outros fetchers remotes.
Não importa LangChain nem tools do agente.
"""
from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable, Sequence
from urllib.parse import urlparse

_ALLOWED_SCHEMES = frozenset({"http", "https"})

# resolve(hostname) -> sequence of IP address strings
ResolveFn = Callable[[str], Sequence[str]]


class UnsafeUrlError(ValueError):
    """URL rejeitada por esquema inválido ou alvo interno/privado (SSRF)."""


def _default_resolve(hostname: str) -> Sequence[str]:
    infos = socket.getaddrinfo(hostname, None)
    return [info[4][0] for info in infos]


def _is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return bool(
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def validate_public_http_url(
    url: str,
    *,
    resolve: ResolveFn | None = None,
) -> None:
    """Garante que `url` é http(s) absoluto apontando para host público.

    Raises:
        UnsafeUrlError: esquema inválido, host ausente, DNS falha, ou IP bloqueado.
    """
    parsed = urlparse(url)
    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise UnsafeUrlError(
            f"Esquema de URL não permitido: {parsed.scheme!r} (use http/https)."
        )
    if not parsed.hostname:
        raise UnsafeUrlError(f"URL sem host válido: {url!r}.")

    hostname = parsed.hostname
    # IP literal no host — checa sem DNS.
    try:
        literal = ipaddress.ip_address(hostname)
    except ValueError:
        literal = None
    if literal is not None:
        if _is_blocked_ip(literal):
            raise UnsafeUrlError(
                f"Host de destino não permitido (privado/loopback): {literal} — SSRF."
            )
        return

    resolver = resolve or _default_resolve
    try:
        addresses = resolver(hostname)
    except OSError as exc:
        raise UnsafeUrlError(
            f"Não foi possível resolver o host da URL: {url!r} ({exc})."
        ) from exc

    if not addresses:
        raise UnsafeUrlError(f"Não foi possível resolver o host da URL: {url!r}.")

    for addr in addresses:
        ip = ipaddress.ip_address(addr)
        if _is_blocked_ip(ip):
            raise UnsafeUrlError(
                f"Host de destino não permitido (privado/loopback): {ip} — SSRF."
            )
