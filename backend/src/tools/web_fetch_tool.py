"""Tool `web_fetch` — lê o conteúdo textual de uma URL HTTP(S) concreta.

Complementa `internet_search` (busca por query). Não usa Tavily nem qualquer
motor de search: o único input obrigatório é a URL.
"""
from __future__ import annotations

import os
from typing import Any
from urllib.parse import urljoin

import httpx
from langchain_core.tools import tool

from src.infrastructure.web.url_safety import UnsafeUrlError, validate_public_http_url
from src.tools.html_text import html_to_text

# Injetável em testes (httpx.MockTransport); None em produção.
_TRANSPORT_OVERRIDE: httpx.BaseTransport | None = None

_DEFAULT_TIMEOUT = 20.0
_DEFAULT_MAX_BYTES = 2 * 1024 * 1024  # 2 MiB
_DEFAULT_MAX_CHARS = 100_000
_DEFAULT_MAX_REDIRECTS = 5
_USER_AGENT = "JeffAI-WebFetch/1.0"

# Patchável nos testes de truncamento.
_MAX_CHARS = _DEFAULT_MAX_CHARS

_TRUNCATION_SUFFIX = "\n\n[...truncated...]"


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _default_timeout() -> float:
    return _env_float("WEB_FETCH_TIMEOUT", _DEFAULT_TIMEOUT)


def _max_bytes() -> int:
    return _env_int("WEB_FETCH_MAX_BYTES", _DEFAULT_MAX_BYTES)


def _max_redirects() -> int:
    return _env_int("WEB_FETCH_MAX_REDIRECTS", _DEFAULT_MAX_REDIRECTS)


def _max_chars() -> int:
    if _MAX_CHARS != _DEFAULT_MAX_CHARS:
        return _MAX_CHARS
    return _env_int("WEB_FETCH_MAX_CHARS", _DEFAULT_MAX_CHARS)


def _error(message: str) -> dict[str, Any]:
    return {"error": message}


def _content_type_base(content_type_header: str) -> str:
    return (content_type_header or "").split(";", 1)[0].strip().lower()


def _is_html(content_type: str, body_prefix: bytes) -> bool:
    if content_type in {"text/html", "application/xhtml+xml"}:
        return True
    if not content_type:
        head = body_prefix.lstrip()[:64].lower()
        return head.startswith(b"<!doctype html") or head.startswith(b"<html")
    return False


def _is_unsupported_binary(content_type: str) -> bool:
    if content_type.startswith("image/"):
        return True
    return content_type in {
        "application/pdf",
        "application/octet-stream",
        "application/zip",
        "application/gzip",
    }


def _truncate(text: str, limit: int) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    return text[: max(0, limit)] + _TRUNCATION_SUFFIX, True


def _download(
    url: str,
    *,
    client: httpx.Client,
    max_bytes: int,
    max_redirects: int,
) -> tuple[str, str, bytes] | dict[str, Any]:
    """GET com redirects manuais + revalidação SSRF.

    Returns:
        (final_url, content_type, body) ou dict de erro.
    """
    current = url
    for _ in range(max_redirects + 1):
        try:
            validate_public_http_url(current)
        except UnsafeUrlError as exc:
            return _error(str(exc))

        try:
            with client.stream("GET", current) as response:
                if response.is_redirect:
                    location = response.headers.get("location")
                    if not location:
                        return _error(
                            f"Redirect HTTP {response.status_code} sem header Location."
                        )
                    current = urljoin(str(response.url), location)
                    continue

                if response.status_code >= 400:
                    return _error(
                        f"Falha HTTP {response.status_code} ao buscar {current!r}."
                    )

                content_type = _content_type_base(
                    response.headers.get("content-type", "")
                )
                final_url = str(response.url)
                chunks: list[bytes] = []
                total = 0
                for chunk in response.iter_bytes():
                    total += len(chunk)
                    if total > max_bytes:
                        remain = max(0, max_bytes - (total - len(chunk)))
                        chunks.append(chunk[:remain])
                        return final_url, content_type, b"".join(chunks)[:max_bytes]
                    chunks.append(chunk)
                return final_url, content_type, b"".join(chunks)
        except httpx.TimeoutException as exc:
            return _error(f"Timeout ao buscar {current!r}: {exc}")
        except httpx.HTTPError as exc:
            return _error(f"Falha de rede ao buscar {current!r}: {exc}")

    return _error(f"Excedido o máximo de redirects ({max_redirects}) para {url!r}.")


@tool
def web_fetch(url: str) -> dict[str, Any]:
    """Fetch the textual content of a specific URL (not a web search).

    Use this when you already have a concrete http(s) link and need to read
    the page. Do NOT use this to search the web by query — use
    `internet_search` (or `search_arxiv`) for search. JavaScript-rendered
    pages may return little text; PDFs/images are not supported here.
    """
    try:
        validate_public_http_url(url)
    except UnsafeUrlError as exc:
        return _error(str(exc))

    timeout = _default_timeout()
    max_bytes = _max_bytes()
    max_redirects = _max_redirects()
    max_chars = _max_chars()

    try:
        with httpx.Client(
            timeout=timeout,
            follow_redirects=False,
            transport=_TRANSPORT_OVERRIDE,
            headers={"User-Agent": _USER_AGENT},
        ) as client:
            downloaded = _download(
                url,
                client=client,
                max_bytes=max_bytes,
                max_redirects=max_redirects,
            )
    except httpx.TimeoutException as exc:
        return _error(f"Timeout ao buscar {url!r}: {exc}")
    except httpx.HTTPError as exc:
        return _error(f"Falha de rede ao buscar {url!r}: {exc}")

    if isinstance(downloaded, dict):
        return downloaded

    final_url, content_type, body = downloaded

    if _is_unsupported_binary(content_type):
        return _error(
            f"Tipo de conteúdo não suportado por web_fetch: {content_type or 'desconhecido'}."
        )

    if _is_html(content_type, body):
        text = html_to_text(body.decode("utf-8", errors="replace"))
    elif content_type.startswith("text/") or not content_type:
        text = body.decode("utf-8", errors="replace")
    else:
        return _error(
            f"Tipo de conteúdo não suportado por web_fetch: {content_type}."
        )

    text = text.strip()
    if not text:
        return _error(f"Nenhum texto legível extraído de {final_url!r}.")

    content, truncated = _truncate(text, max_chars)
    return {
        "url": final_url,
        "content": content,
        "truncated": truncated,
        "content_type": content_type or "text/html",
    }
