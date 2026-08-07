"""Testes de `src/infrastructure/web/delivery_tokens.py`.

Cobre a task `fix-whatsapp-document-delivery-task-foundation-1` (REQ-013 de
`whatsapp-channel`): token de entrega de uso único, para que o WhatsApp
(Evolution API) consiga buscar um attachment via URL pública sem sessão,
sem expor `/api/files`/`/api/images` (que são autenticadas e checam
ownership por usuário).
"""
from __future__ import annotations

import time

from src.infrastructure.web import delivery_tokens


def test_mint_and_resolve_delivery_token_is_single_use() -> None:
    """fix-whatsapp-document-delivery-task-foundation-1-unit-1."""
    token = delivery_tokens.mint_delivery_token(
        "/tmp/foo.docx", "foo.docx", "application/vnd.test", ttl_seconds=600
    )

    payload = delivery_tokens.resolve_delivery_token(token)

    assert payload == {
        "file_path": "/tmp/foo.docx",
        "filename": "foo.docx",
        "mime": "application/vnd.test",
    }
    assert delivery_tokens.resolve_delivery_token(token) is None


def test_resolve_delivery_token_returns_none_when_expired() -> None:
    """fix-whatsapp-document-delivery-task-foundation-1-unit-2."""
    token = delivery_tokens.mint_delivery_token(
        "/tmp/foo.docx", "foo.docx", "application/vnd.test", ttl_seconds=0
    )
    time.sleep(0.01)

    assert delivery_tokens.resolve_delivery_token(token) is None


def test_resolve_delivery_token_returns_none_when_never_minted() -> None:
    """fix-whatsapp-document-delivery-task-foundation-1-unit-2."""
    assert delivery_tokens.resolve_delivery_token("never-minted") is None
