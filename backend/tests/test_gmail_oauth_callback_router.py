"""Testes de `GET /api/email/accounts/gmail/callback`
(task `gmail-account-oauth-connection-task-routes-2`).

REQ-002/REQ-004 do spec `gmail-oauth-connection`: valida o `state`
double-submit contra o cookie `gmail_oauth_state`, troca o `code` via
`CompleteGmailOAuth` (dependências sobrescritas em teste), e redireciona o
browser para `{FRONTEND_ORIGIN}/email?gmail_connected=1|0`.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

import src.infrastructure.web.email_router as email_router
import src.infrastructure.web.webapp as webapp
from src.application.ports.email_account_repository import (
    EmailAccountRepositoryPort,
)
from src.application.ports.user_integration_repository import (
    UserIntegrationRepositoryPort,
)
from src.domain.email import EmailAccount
from src.domain.integrations import UserIntegration
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


class _FakeEmailAccountRepository(EmailAccountRepositoryPort):
    def __init__(self) -> None:
        self.accounts: dict[str, EmailAccount] = {}

    async def create(self, account: EmailAccount) -> EmailAccount:
        self.accounts[account.id] = account
        return account

    async def get(self, user_id: str, account_id: str) -> EmailAccount | None:
        account = self.accounts.get(account_id)
        if account is None or account.user_id != user_id:
            return None
        return account

    async def list_by_user(self, user_id: str) -> list[EmailAccount]:
        return [a for a in self.accounts.values() if a.user_id == user_id]

    async def list_all(self) -> list[EmailAccount]:
        return list(self.accounts.values())

    async def update(self, account: EmailAccount) -> EmailAccount | None:
        existing = self.accounts.get(account.id)
        if existing is None or existing.user_id != account.user_id:
            return None
        self.accounts[account.id] = account
        return account

    async def delete(self, user_id: str, account_id: str) -> bool:
        existing = self.accounts.get(account_id)
        if existing is None or existing.user_id != user_id:
            return False
        del self.accounts[account_id]
        return True


class _FakeUserIntegrationRepository(UserIntegrationRepositoryPort):
    def __init__(self) -> None:
        self.integrations: dict[str, UserIntegration] = {}

    async def save(self, integration: UserIntegration) -> None:
        self.integrations[integration.id] = integration

    async def get(self, integration_id: str) -> UserIntegration | None:
        return self.integrations.get(integration_id)

    async def list_by_user(self, user_id: str) -> list[UserIntegration]:
        return [i for i in self.integrations.values() if i.user_id == user_id]

    async def list_all(self) -> list[UserIntegration]:
        return list(self.integrations.values())

    async def delete(self, integration_id: str) -> None:
        self.integrations.pop(integration_id, None)


@dataclass(frozen=True)
class _FakeTokenResult:
    access_token: str
    refresh_token: str
    expires_in: int
    email_address: str


_exchange_calls: list[str] = []


async def _always_ok_exchange(code: str) -> _FakeTokenResult:
    _exchange_calls.append(code)
    return _FakeTokenResult(
        access_token="ya29.access",
        refresh_token="1//refresh",
        expires_in=3599,
        email_address="user@gmail.com",
    )


@pytest.fixture(autouse=True)
def _reset_exchange_calls():
    _exchange_calls.clear()
    yield
    _exchange_calls.clear()


@pytest.fixture
def accounts_repo() -> _FakeEmailAccountRepository:
    return _FakeEmailAccountRepository()


@pytest.fixture
def integrations_repo() -> _FakeUserIntegrationRepository:
    return _FakeUserIntegrationRepository()


@pytest.fixture
def client(
    accounts_repo: _FakeEmailAccountRepository,
    integrations_repo: _FakeUserIntegrationRepository,
):
    webapp.app.dependency_overrides[email_router._email_account_repository] = (
        lambda: accounts_repo
    )
    webapp.app.dependency_overrides[email_router._user_integration_repository] = (
        lambda: integrations_repo
    )
    webapp.app.dependency_overrides[email_router._gmail_exchange_code_for_tokens] = (
        lambda: _always_ok_exchange
    )
    webapp.app.dependency_overrides[require_auth] = lambda: _USER_A
    try:
        yield TestClient(webapp.app, follow_redirects=False)
    finally:
        webapp.app.dependency_overrides.pop(require_auth, None)
        webapp.app.dependency_overrides.pop(
            email_router._email_account_repository, None
        )
        webapp.app.dependency_overrides.pop(
            email_router._user_integration_repository, None
        )
        webapp.app.dependency_overrides.pop(
            email_router._gmail_exchange_code_for_tokens, None
        )


def test_callback_state_mismatch_returns_400_and_calls_nothing(
    client: TestClient,
) -> None:
    """gmail-account-oauth-connection-task-routes-2-unit-1 (REQ-002)."""
    client.cookies.set(email_router.GMAIL_OAUTH_STATE_COOKIE_NAME, "cookie-state")

    resp = client.get(
        "/api/email/accounts/gmail/callback",
        params={"code": "auth-code", "state": "wrong-state"},
    )

    assert resp.status_code == 400
    assert _exchange_calls == []


def test_callback_missing_state_cookie_returns_400(client: TestClient) -> None:
    """gmail-account-oauth-connection-task-routes-2-unit-1 (REQ-002)."""
    resp = client.get(
        "/api/email/accounts/gmail/callback",
        params={"code": "auth-code", "state": "some-state"},
    )

    assert resp.status_code == 400
    assert _exchange_calls == []


def test_callback_user_denied_redirects_with_gmail_connected_zero(
    client: TestClient,
) -> None:
    """gmail-account-oauth-connection-task-routes-2-unit-2 (REQ-004)."""
    client.cookies.set(email_router.GMAIL_OAUTH_STATE_COOKIE_NAME, "matching-state")

    resp = client.get(
        "/api/email/accounts/gmail/callback",
        params={"error": "access_denied", "state": "matching-state"},
    )

    assert resp.status_code == 302
    assert resp.headers["location"].endswith("/email?gmail_connected=0")
    assert _exchange_calls == []


def test_callback_success_redirects_with_gmail_connected_one(
    client: TestClient,
    accounts_repo: _FakeEmailAccountRepository,
    integrations_repo: _FakeUserIntegrationRepository,
) -> None:
    """gmail-account-oauth-connection-task-routes-2-unit-3 (REQ-002)."""
    client.cookies.set(email_router.GMAIL_OAUTH_STATE_COOKIE_NAME, "matching-state")

    resp = client.get(
        "/api/email/accounts/gmail/callback",
        params={"code": "auth-code", "state": "matching-state"},
    )

    assert resp.status_code == 302
    assert resp.headers["location"].endswith("/email?gmail_connected=1")
    assert _exchange_calls == ["auth-code"]
    assert len(accounts_repo.accounts) == 1
    assert len(integrations_repo.integrations) == 1
    set_cookie = resp.headers.get("set-cookie", "")
    assert email_router.GMAIL_OAUTH_STATE_COOKIE_NAME in set_cookie
