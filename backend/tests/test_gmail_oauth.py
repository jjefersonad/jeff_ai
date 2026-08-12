"""Testes de `src/infrastructure/email/gmail_oauth.py`.

Cobre a task `gmail-account-oauth-connection-task-oauth-1`: construção da
URL de autorização OAuth2 do Google (REQ-001 do spec `gmail-oauth-connection`).
"""
from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
import respx

from src.application.ports.user_integration_repository import (
    UserIntegrationRepositoryPort,
)
from src.domain.integrations import UserIntegration
from src.infrastructure.email import gmail_oauth


class _FakeUserIntegrationRepository(UserIntegrationRepositoryPort):
    def __init__(self) -> None:
        self.integrations: dict[str, UserIntegration] = {}
        self.save_calls: list[UserIntegration] = []

    async def save(self, integration: UserIntegration) -> None:
        self.save_calls.append(integration)
        self.integrations[integration.id] = integration

    async def get(self, integration_id: str) -> UserIntegration | None:
        return self.integrations.get(integration_id)

    async def list_by_user(self, user_id: str) -> list[UserIntegration]:
        return [i for i in self.integrations.values() if i.user_id == user_id]

    async def list_all(self) -> list[UserIntegration]:
        return list(self.integrations.values())

    async def delete(self, integration_id: str) -> None:
        self.integrations.pop(integration_id, None)


def _sample_gmail_integration(*, token_expiry: datetime) -> UserIntegration:
    return UserIntegration(
        id="integration-1",
        user_id="user-1",
        integration_type="gmail",
        config={
            "email_address": "user@gmail.com",
            "access_token": "ya29.old",
            "refresh_token": "1//refresh",
            "token_expiry": token_expiry.isoformat(),
        },
    )


def _fake_id_token(email: str) -> str:
    """JWT sem assinatura real — só o payload importa (`_decode_id_token_email`)."""
    payload = (
        base64.urlsafe_b64encode(json.dumps({"email": email}).encode())
        .decode()
        .rstrip("=")
    )
    return f"header.{payload}.signature"


def test_build_authorize_url_contains_expected_params(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """gmail-account-oauth-connection-task-oauth-1-unit-1 (REQ-001)."""
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "client-123")
    monkeypatch.setenv(
        "GOOGLE_OAUTH_REDIRECT_URI",
        "https://example.com/api/email/accounts/gmail/callback",
    )

    url = gmail_oauth.build_authorize_url("abc123")

    parsed = urlparse(url)
    assert parsed.netloc == "accounts.google.com"
    assert parsed.path == "/o/oauth2/v2/auth"
    params = parse_qs(parsed.query)
    assert params["client_id"] == ["client-123"]
    assert params["redirect_uri"] == [
        "https://example.com/api/email/accounts/gmail/callback"
    ]
    assert params["response_type"] == ["code"]
    assert params["access_type"] == ["offline"]
    assert params["prompt"] == ["consent"]
    assert params["state"] == ["abc123"]
    scope = params["scope"][0]
    assert "https://mail.google.com/" in scope


@pytest.mark.parametrize(
    "missing_var", ["GOOGLE_OAUTH_CLIENT_ID", "GOOGLE_OAUTH_REDIRECT_URI"]
)
def test_build_authorize_url_raises_clear_error_when_env_missing(
    monkeypatch: pytest.MonkeyPatch, missing_var: str
) -> None:
    """gmail-account-oauth-connection-task-oauth-1-unit-2 (REQ-001)."""
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "client-123")
    monkeypatch.setenv("GOOGLE_OAUTH_REDIRECT_URI", "https://example.com/callback")
    monkeypatch.delenv(missing_var, raising=False)

    with pytest.raises(gmail_oauth.MissingGoogleOAuthConfigError) as exc_info:
        gmail_oauth.build_authorize_url("abc123")

    assert missing_var in str(exc_info.value)


@respx.mock
async def test_exchange_code_for_tokens_happy_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """gmail-account-oauth-connection-task-oauth-2-unit-1 (REQ-002)."""
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "client-123")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "secret-456")
    monkeypatch.setenv("GOOGLE_OAUTH_REDIRECT_URI", "https://example.com/callback")

    respx.post("https://oauth2.googleapis.com/token").mock(
        return_value=httpx.Response(
            200,
            json={
                "access_token": "ya29.access",
                "refresh_token": "1//refresh",
                "expires_in": 3599,
                "id_token": _fake_id_token("user@gmail.com"),
            },
        )
    )

    result = await gmail_oauth.exchange_code_for_tokens("auth-code")

    assert result.access_token == "ya29.access"
    assert result.refresh_token == "1//refresh"
    assert result.expires_in == 3599
    assert result.email_address == "user@gmail.com"


@respx.mock
async def test_exchange_code_for_tokens_missing_refresh_token_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """gmail-account-oauth-connection-task-oauth-2-unit-2 (REQ-002)."""
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "client-123")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "secret-456")
    monkeypatch.setenv("GOOGLE_OAUTH_REDIRECT_URI", "https://example.com/callback")

    respx.post("https://oauth2.googleapis.com/token").mock(
        return_value=httpx.Response(
            200,
            json={
                "access_token": "ya29.access",
                "expires_in": 3599,
                "id_token": _fake_id_token("user@gmail.com"),
            },
        )
    )

    with pytest.raises(gmail_oauth.MissingRefreshTokenError):
        await gmail_oauth.exchange_code_for_tokens("auth-code")


@respx.mock
async def test_refresh_access_token_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """gmail-account-oauth-connection-task-oauth-3-unit-1 (REQ-003)."""
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "client-123")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "secret-456")

    respx.post("https://oauth2.googleapis.com/token").mock(
        return_value=httpx.Response(
            200, json={"access_token": "ya29.new", "expires_in": 3599}
        )
    )

    before = datetime.now(UTC)
    result = await gmail_oauth.refresh_access_token("1//refresh")
    after = datetime.now(UTC)

    assert result.access_token == "ya29.new"
    assert before + timedelta(seconds=3599) <= result.expiry <= after + timedelta(
        seconds=3599
    )


@respx.mock
async def test_refresh_access_token_revoked_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """gmail-account-oauth-connection-task-oauth-3-unit-2 (REQ-003)."""
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "client-123")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "secret-456")

    respx.post("https://oauth2.googleapis.com/token").mock(
        return_value=httpx.Response(400, json={"error": "invalid_grant"})
    )

    with pytest.raises(gmail_oauth.RefreshTokenRevokedError):
        await gmail_oauth.refresh_access_token("1//revoked")


async def test_ensure_fresh_token_not_expired_is_a_noop() -> None:
    """gmail-account-oauth-connection-task-oauth-4-unit-1 (REQ-003)."""
    repo = _FakeUserIntegrationRepository()
    future = datetime.now(UTC) + timedelta(hours=1)
    integration = _sample_gmail_integration(token_expiry=future)

    result = await gmail_oauth.ensure_fresh_token(integration, repo)

    assert result.access_token == "ya29.old"
    assert repo.save_calls == []


@respx.mock
async def test_ensure_fresh_token_expired_refreshes_and_persists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """gmail-account-oauth-connection-task-oauth-4-unit-2 (REQ-003)."""
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "client-123")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "secret-456")
    respx.post("https://oauth2.googleapis.com/token").mock(
        return_value=httpx.Response(
            200, json={"access_token": "ya29.new", "expires_in": 3599}
        )
    )
    repo = _FakeUserIntegrationRepository()
    past = datetime.now(UTC) - timedelta(minutes=1)
    integration = _sample_gmail_integration(token_expiry=past)

    result = await gmail_oauth.ensure_fresh_token(integration, repo)

    assert result.access_token == "ya29.new"
    assert len(repo.save_calls) == 1
    saved = repo.save_calls[0]
    assert saved.id == "integration-1"
    assert saved.config["access_token"] == "ya29.new"


@respx.mock
async def test_ensure_fresh_token_revoked_propagates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """gmail-account-oauth-connection-task-oauth-4-unit-3 (REQ-003)."""
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "client-123")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "secret-456")
    respx.post("https://oauth2.googleapis.com/token").mock(
        return_value=httpx.Response(400, json={"error": "invalid_grant"})
    )
    repo = _FakeUserIntegrationRepository()
    past = datetime.now(UTC) - timedelta(minutes=1)
    integration = _sample_gmail_integration(token_expiry=past)

    with pytest.raises(gmail_oauth.RefreshTokenRevokedError):
        await gmail_oauth.ensure_fresh_token(integration, repo)

    assert repo.save_calls == []
