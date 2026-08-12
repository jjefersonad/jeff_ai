"""Testes de `src/application/use_cases/complete_gmail_oauth.py`.

Cobre a task `gmail-account-oauth-connection-task-accounts-2`:
`CompleteGmailOAuth` troca `code` pelos tokens Gmail e persiste
`UserIntegration` + `EmailAccount` (`provider="gmail"`), fail-fast igual
`ConnectEmailAccount` — nenhuma linha é persistida se a troca falhar
(REQ-002 do spec `gmail-oauth-connection`).
"""
from __future__ import annotations

from dataclasses import dataclass

import pytest

from src.application.ports.email_account_repository import (
    EmailAccountRepositoryPort,
)
from src.application.ports.user_integration_repository import (
    UserIntegrationRepositoryPort,
)
from src.application.use_cases.complete_gmail_oauth import CompleteGmailOAuth
from src.domain.email import EmailAccount, EmailAccountStatus
from src.domain.integrations import UserIntegration
from src.infrastructure.email.gmail_oauth import MissingRefreshTokenError


class _FakeEmailAccountRepository(EmailAccountRepositoryPort):
    def __init__(self) -> None:
        self.accounts: dict[str, EmailAccount] = {}
        self.create_calls = 0

    async def create(self, account: EmailAccount) -> EmailAccount:
        self.create_calls += 1
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


async def _always_ok_exchange(code: str) -> _FakeTokenResult:
    return _FakeTokenResult(
        access_token="ya29.access",
        refresh_token="1//refresh",
        expires_in=3599,
        email_address="user@gmail.com",
    )


async def test_complete_gmail_oauth_happy_path_persists_integration_and_account() -> None:
    """gmail-account-oauth-connection-task-accounts-2-unit-1 (REQ-002)."""
    repository = _FakeEmailAccountRepository()
    integration_repository = _FakeUserIntegrationRepository()
    use_case = CompleteGmailOAuth(
        repository=repository,
        integration_repository=integration_repository,
        exchange_code_for_tokens=_always_ok_exchange,
    )

    account = await use_case.execute(user_id="user-1", code="auth-code")

    assert account.user_id == "user-1"
    assert account.provider == "gmail"
    assert account.status == EmailAccountStatus.CONNECTED
    assert len(repository.accounts) == 1
    assert len(integration_repository.integrations) == 1
    saved_integration = integration_repository.integrations[account.user_integration_id]
    assert saved_integration.integration_type == "gmail"
    assert saved_integration.config["email_address"] == "user@gmail.com"
    assert saved_integration.config["access_token"] == "ya29.access"


async def test_complete_gmail_oauth_missing_refresh_token_persists_nothing() -> None:
    """gmail-account-oauth-connection-task-accounts-2-unit-2 (REQ-002)."""
    repository = _FakeEmailAccountRepository()
    integration_repository = _FakeUserIntegrationRepository()

    async def _failing_exchange(code: str) -> _FakeTokenResult:
        raise MissingRefreshTokenError("no refresh_token")

    use_case = CompleteGmailOAuth(
        repository=repository,
        integration_repository=integration_repository,
        exchange_code_for_tokens=_failing_exchange,
    )

    with pytest.raises(MissingRefreshTokenError):
        await use_case.execute(user_id="user-1", code="auth-code")

    assert repository.accounts == {}
    assert integration_repository.integrations == {}


async def test_complete_gmail_oauth_reconnect_updates_existing_account_and_tokens() -> None:
    """gmail-account-oauth-connection-task-accounts-3-unit-1 (REQ-005)."""
    repository = _FakeEmailAccountRepository()
    integration_repository = _FakeUserIntegrationRepository()

    await integration_repository.save(
        UserIntegration(
            id="integration-1",
            user_id="user-1",
            integration_type="gmail",
            config={
                "email_address": "user@gmail.com",
                "access_token": "ya29.old",
                "refresh_token": "1//old-refresh",
                "token_expiry": "2020-01-01T00:00:00+00:00",
            },
        )
    )
    await repository.create(
        EmailAccount(
            id="account-1",
            user_id="user-1",
            user_integration_id="integration-1",
            display_name="user@gmail.com",
            provider="gmail",
            status=EmailAccountStatus.ERROR,
        )
    )
    repository.create_calls = 0  # reset — only reconnect's call count is under test

    use_case = CompleteGmailOAuth(
        repository=repository,
        integration_repository=integration_repository,
        exchange_code_for_tokens=_always_ok_exchange,
    )

    account = await use_case.execute(user_id="user-1", code="auth-code")

    assert account.id == "account-1"
    assert account.status == EmailAccountStatus.CONNECTED
    assert repository.create_calls == 0
    assert len(repository.accounts) == 1
    saved_integration = integration_repository.integrations["integration-1"]
    assert saved_integration.config["access_token"] == "ya29.access"
