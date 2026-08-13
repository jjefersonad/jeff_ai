"""Testes de `POST /api/email/accounts/gmail/authorize`
(task `gmail-account-oauth-connection-task-routes-1`).

REQ-001 do spec `gmail-oauth-connection`: requer sessão, monta a URL de
consentimento do Google via `StartGmailOAuth` (`build_authorize_url`
sobrescrito em teste) e seta o cookie de state `gmail_oauth_state`.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

import src.infrastructure.web.email_router as email_router
import src.infrastructure.web.webapp as webapp
from src.infrastructure.auth.dependencies import require_auth
from src.infrastructure.auth.users import User

_USER_A = User(
    id="user-a",
    username="alice",
    password_hash="h",
    role="user",
    is_active=True,
    created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
)


def _fake_build_authorize_url(state: str) -> str:
    return f"https://accounts.google.com/o/oauth2/v2/auth?state={state}"


@pytest.fixture
def client():
    webapp.app.dependency_overrides[email_router._gmail_build_authorize_url] = (
        lambda: _fake_build_authorize_url
    )
    try:
        yield TestClient(webapp.app)
    finally:
        webapp.app.dependency_overrides.pop(require_auth, None)
        webapp.app.dependency_overrides.pop(
            email_router._gmail_build_authorize_url, None
        )


def test_authorize_unauthenticated_returns_401_and_no_state_cookie(
    client: TestClient,
) -> None:
    """gmail-account-oauth-connection-task-routes-1-unit-1 (REQ-001)."""
    resp = client.post("/api/email/accounts/gmail/authorize")

    assert resp.status_code == 401
    assert email_router.GMAIL_OAUTH_STATE_COOKIE_NAME not in resp.cookies


def test_authorize_authenticated_returns_url_and_sets_state_cookie(
    client: TestClient,
) -> None:
    """gmail-account-oauth-connection-task-routes-1-unit-2 (REQ-001)."""
    webapp.app.dependency_overrides[require_auth] = lambda: _USER_A

    resp = client.post("/api/email/accounts/gmail/authorize")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["authorize_url"].startswith(
        "https://accounts.google.com/o/oauth2/v2/auth?state="
    )
    assert email_router.GMAIL_OAUTH_STATE_COOKIE_NAME in resp.cookies
    set_cookie_header = resp.headers.get("set-cookie", "")
    assert "httponly" in set_cookie_header.lower()
