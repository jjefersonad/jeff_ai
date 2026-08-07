"""Testes de `src/infrastructure/web/media_delivery_router.py`.

Cobre a task `fix-whatsapp-document-delivery-task-foundation-1` (REQ-014 de
`whatsapp-channel`): `GET /public/media-delivery/{token}` serve o arquivo de
um token válido SEM sessão autenticada (rota pública, sob `/public/`), e
responde 404 para token ausente/expirado/já consumido.
"""
from __future__ import annotations

import time
from pathlib import Path

from fastapi.testclient import TestClient

import src.infrastructure.web.webapp as webapp
from src.infrastructure.web import delivery_tokens


def test_valid_token_serves_file_without_auth(tmp_path: Path) -> None:
    """fix-whatsapp-document-delivery-task-foundation-1-unit-3."""
    file_path = tmp_path / "foo.txt"
    file_path.write_bytes(b"conteudo do teste")
    token = delivery_tokens.mint_delivery_token(str(file_path), "foo.txt", "text/plain")

    client = TestClient(webapp.app)
    response = client.get(f"/public/media-delivery/{token}")

    assert response.status_code == 200
    assert response.content == b"conteudo do teste"
    assert response.headers["content-type"].startswith("text/plain")


def test_unknown_token_returns_404() -> None:
    """fix-whatsapp-document-delivery-task-foundation-1-unit-4."""
    client = TestClient(webapp.app)

    response = client.get("/public/media-delivery/never-minted")

    assert response.status_code == 404


def test_already_consumed_token_returns_404_on_second_request(tmp_path: Path) -> None:
    """fix-whatsapp-document-delivery-task-foundation-1-unit-4."""
    file_path = tmp_path / "foo.txt"
    file_path.write_bytes(b"conteudo do teste")
    token = delivery_tokens.mint_delivery_token(str(file_path), "foo.txt", "text/plain")
    client = TestClient(webapp.app)
    first = client.get(f"/public/media-delivery/{token}")
    assert first.status_code == 200

    second = client.get(f"/public/media-delivery/{token}")

    assert second.status_code == 404


def test_expired_token_returns_404(tmp_path: Path) -> None:
    """fix-whatsapp-document-delivery-task-foundation-1-unit-4."""
    file_path = tmp_path / "foo.txt"
    file_path.write_bytes(b"conteudo do teste")
    token = delivery_tokens.mint_delivery_token(
        str(file_path), "foo.txt", "text/plain", ttl_seconds=0
    )
    time.sleep(0.01)
    client = TestClient(webapp.app)

    response = client.get(f"/public/media-delivery/{token}")

    assert response.status_code == 404
