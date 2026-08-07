"""Origem pública absoluta para URLs de mídia devolvidas pelas tools.

Precedência (return-public-image-url):
`NEXT_PUBLIC_API_URL` → `BASE_URL` → `FRONTEND_ORIGIN` → `http://localhost:3000`.
"""
from __future__ import annotations

import os

_DEFAULT_ORIGIN = "http://localhost:3000"


def public_api_origin() -> str:
    """Resolve a origem HTTP(S) pública do backend, sem barra final."""
    raw = (
        os.getenv("NEXT_PUBLIC_API_URL")
        or os.getenv("BASE_URL")
        or os.getenv("FRONTEND_ORIGIN")
        or _DEFAULT_ORIGIN
    )
    return raw.strip().rstrip("/")


def image_url_prefix() -> str:
    """Prefixo absoluto para PNGs servidos em ``GET /api/images/{filename}``."""
    return f"{public_api_origin()}/api/images"
