"""Testes de `POST /api/integrations/whatsapp/link-code`
(task `whatsapp-evolution-channel-task-linking-2`).

Cobre o unit-test linkado à task no OpenSddRag:

- unit-1 (whatsapp-channel REQ-001): POST autenticado retorna um código de 6
  caracteres alfanuméricos, e a entrada persistida em `whatsapp_link_codes`
  tem `expires_at` ~10 minutos após a emissão e `user_id` igual ao chamador.

Persistência é um fake injetado via override de dependency, mesmo padrão de
`test_telegram_link_code_endpoint.py`.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

import src.infrastructure.web.integrations_router as integrations_router
import src.infrastructure.web.webapp as webapp
from src.application.ports.whatsapp_link_code_repository import (
    WhatsAppLinkCodeRepositoryPort,
)
from src.domain.integrations import WhatsAppLinkCode
from src.infrastructure.auth.dependencies import require_auth
from src.infrastructure.auth.users import User

_USER_A = User(id="user-a", username="bob", password_hash="h", role="user", is_active=True)


class _FakeWhatsAppLinkCodeRepository(WhatsAppLinkCodeRepositoryPort):
    def __init__(self) -> None:
        self.saved: list[WhatsAppLinkCode] = []
        self._by_code: dict[str, WhatsAppLinkCode] = {}

    async def save(self, link_code: WhatsAppLinkCode) -> None:
        self.saved.append(link_code)
        self._by_code[link_code.code] = link_code

    async def get(self, code: str) -> WhatsAppLinkCode | None:
        return self._by_code.get(code)

    async def delete(self, code: str) -> None:
        self._by_code.pop(code, None)


@pytest.fixture
def repo() -> _FakeWhatsAppLinkCodeRepository:
    return _FakeWhatsAppLinkCodeRepository()


@pytest.fixture
def client(repo: _FakeWhatsAppLinkCodeRepository):
    webapp.app.dependency_overrides[
        integrations_router._whatsapp_link_code_repository
    ] = lambda: repo
    webapp.app.dependency_overrides[require_auth] = lambda: _USER_A
    try:
        yield TestClient(webapp.app)
    finally:
        webapp.app.dependency_overrides.pop(require_auth, None)
        webapp.app.dependency_overrides.pop(
            integrations_router._whatsapp_link_code_repository, None
        )


def test_create_link_code_returns_six_char_alphanumeric_code(
    client: TestClient,
) -> None:
    """whatsapp-evolution-channel-task-linking-2-unit-1 (parte 1)."""
    resp = client.post("/api/integrations/whatsapp/link-code")

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert len(body["code"]) == 6
    assert body["code"].isalnum()


def test_create_link_code_persists_row_tied_to_caller_with_ten_minute_ttl(
    client: TestClient, repo: _FakeWhatsAppLinkCodeRepository
) -> None:
    """whatsapp-evolution-channel-task-linking-2-unit-1 (parte 2)."""
    before = datetime.now(UTC)

    resp = client.post("/api/integrations/whatsapp/link-code")

    assert resp.status_code == 201, resp.text
    assert len(repo.saved) == 1
    saved = repo.saved[0]
    assert saved.user_id == "user-a"
    assert saved.code == resp.json()["code"]

    expected_expiry = before + timedelta(minutes=10)
    assert abs((saved.expires_at - expected_expiry).total_seconds()) < 5


def test_create_link_code_without_session_is_unauthorized(client: TestClient) -> None:
    webapp.app.dependency_overrides.pop(require_auth, None)

    resp = client.post("/api/integrations/whatsapp/link-code")

    assert resp.status_code == 401
