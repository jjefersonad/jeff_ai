"""Testes de `GET`/`POST /api/email/accounts`, `GET`/`PUT`/`DELETE /api/email/accounts/{id}`
(task `email-client-imap-mvp-task-accounts-3`).

Cobre os 2 unit-tests linkados à task no OpenSddRag:

- unit-1 (REQ-001): POST com config válido retorna 201 sem ecoar
  imap_password/smtp_password em texto puro; GET de conta de outro usuário
  retorna 404.
- unit-2 (REQ-004): DELETE de conta própria retorna 204 e ela some da listagem.

Persistência é um fake injetado via override de dependency, mesmo padrão de
`test_integrations_router.py`. `verify_login` também é sobrescrito para não
bater em rede de verdade.
"""
from __future__ import annotations

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
_USER_B = User(
    id="user-b",
    username="bob",
    password_hash="h",
    role="user",
    is_active=True,
    created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
)

_VALID_BODY = {
    "display_name": "Trabalho",
    "imap_host": "imap.example.com",
    "imap_port": 993,
    "imap_username": "user@example.com",
    "imap_password": "s3cr3t-imap",
    "smtp_host": "smtp.example.com",
    "smtp_port": 587,
}


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


async def _always_ok_verify_login(config: object) -> None:
    return None


@pytest.fixture
def accounts_repo() -> _FakeEmailAccountRepository:
    return _FakeEmailAccountRepository()


@pytest.fixture
def integrations_repo() -> _FakeUserIntegrationRepository:
    return _FakeUserIntegrationRepository()


@pytest.fixture
def client(accounts_repo: _FakeEmailAccountRepository, integrations_repo: _FakeUserIntegrationRepository):
    webapp.app.dependency_overrides[email_router._email_account_repository] = (
        lambda: accounts_repo
    )
    webapp.app.dependency_overrides[email_router._user_integration_repository] = (
        lambda: integrations_repo
    )
    webapp.app.dependency_overrides[email_router._verify_imap_login] = (
        lambda: _always_ok_verify_login
    )
    try:
        yield TestClient(webapp.app)
    finally:
        webapp.app.dependency_overrides.pop(require_auth, None)
        webapp.app.dependency_overrides.pop(
            email_router._email_account_repository, None
        )
        webapp.app.dependency_overrides.pop(
            email_router._user_integration_repository, None
        )
        webapp.app.dependency_overrides.pop(email_router._verify_imap_login, None)


def _as(user: User) -> None:
    webapp.app.dependency_overrides[require_auth] = lambda: user


# ===========================================================================
# unit-1 (REQ-001): POST não ecoa credenciais; GET cross-user -> 404
# ===========================================================================


def test_connect_does_not_echo_plaintext_credentials(client: TestClient) -> None:
    _as(_USER_A)

    resp = client.post("/api/email/accounts", json=_VALID_BODY)

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["user_id"] == "user-a"
    assert body["display_name"] == "Trabalho"
    assert "s3cr3t-imap" not in resp.text
    assert "imap_password" not in body
    assert "smtp_password" not in body


def test_get_other_users_account_returns_404(
    client: TestClient, accounts_repo: _FakeEmailAccountRepository
) -> None:
    _as(_USER_A)
    created = client.post("/api/email/accounts", json=_VALID_BODY).json()

    _as(_USER_B)
    resp = client.get(f"/api/email/accounts/{created['id']}")

    assert resp.status_code == 404


def test_list_accounts_returns_correct_provider_for_mixed_accounts(
    client: TestClient, accounts_repo: _FakeEmailAccountRepository
) -> None:
    """gmail-account-oauth-connection-task-response-1-unit-1 (REQ-007)."""
    _as(_USER_A)
    imap_account = client.post("/api/email/accounts", json=_VALID_BODY).json()

    gmail_account = EmailAccount(
        id="gmail-account-1",
        user_id=_USER_A.id,
        user_integration_id="gmail-integration-1",
        display_name="user@gmail.com",
        provider="gmail",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    accounts_repo.accounts[gmail_account.id] = gmail_account

    resp = client.get("/api/email/accounts")

    assert resp.status_code == 200
    providers = {item["id"]: item["provider"] for item in resp.json()}
    assert providers[imap_account["id"]] == "imap"
    assert providers[gmail_account.id] == "gmail"


# ===========================================================================
# unit-2 (REQ-004): DELETE remove e some da listagem
# ===========================================================================


def test_delete_removes_account_from_list(client: TestClient) -> None:
    _as(_USER_A)
    created = client.post("/api/email/accounts", json=_VALID_BODY).json()

    delete_resp = client.delete(f"/api/email/accounts/{created['id']}")
    assert delete_resp.status_code == 204

    list_resp = client.get("/api/email/accounts")
    assert list_resp.status_code == 200
    assert created["id"] not in [a["id"] for a in list_resp.json()]


# ===========================================================================
# email-account-edit-connection: tests for `PATCH /api/email/accounts/{id}`
#
# unit-1 (REQ-002): happy path returns 200 with the updated account; the
#   response body never echoes imap_password/smtp_password.
# unit-2 (REQ-003): cross-user PATCH returns 404 with no field-level detail.
# unit-3 (REQ-003): unauthenticated PATCH returns 401.
# unit-4 (REQ-002): payload missing a required field returns 422; no row
#   is modified.
# ===========================================================================


def test_patch_account_happy_path_does_not_echo_credentials(
    client: TestClient,
) -> None:
    _as(_USER_A)
    created = client.post("/api/email/accounts", json=_VALID_BODY).json()
    account_id = created["id"]

    patch_body = {
        "display_name": "Trabalho (renamed)",
        "imap_host": "new.host.example.com",
        "imap_port": 143,
        "imap_username": "user@example.com",
        "imap_password": "new-imap-password",
        "smtp_host": "smtp.example.com",
        "smtp_port": 587,
        "smtp_username": "user@example.com",
        "smtp_password": "new-smtp-password",
    }
    resp = client.patch(f"/api/email/accounts/{account_id}", json=patch_body)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["id"] == account_id
    assert body["display_name"] == "Trabalho (renamed)"
    # Plaintext credentials never echoed.
    assert "new-imap-password" not in resp.text
    assert "new-smtp-password" not in resp.text
    assert "imap_password" not in body
    assert "smtp_password" not in body


def test_patch_account_cross_user_returns_404(
    client: TestClient,
) -> None:
    _as(_USER_A)
    created = client.post("/api/email/accounts", json=_VALID_BODY).json()

    _as(_USER_B)
    patch_body = {
        "imap_host": "hijacked.example.com",
        "imap_port": 993,
        "imap_username": "user@example.com",
        "smtp_host": "smtp.example.com",
        "smtp_port": 587,
    }
    resp = client.patch(f"/api/email/accounts/{created['id']}", json=patch_body)

    assert resp.status_code == 404, resp.text
    body = resp.json()
    # No field-level detail about the existing row.
    detail = str(body.get("detail", ""))
    assert "imap_host" not in detail
    assert "hijacked" not in detail


def test_patch_account_unauthenticated_returns_401(
    client: TestClient,
) -> None:
    # Seed an account as user A so we can confirm nothing is mutated.
    webapp.app.dependency_overrides[require_auth] = lambda: _USER_A
    created = client.post("/api/email/accounts", json=_VALID_BODY).json()
    account_id = created["id"]

    # Now drop the auth override so the next PATCH is unauthenticated.
    webapp.app.dependency_overrides.pop(require_auth, None)

    patch_body = {
        "imap_host": "hijacked.example.com",
        "imap_port": 993,
        "imap_username": "user@example.com",
        "smtp_host": "smtp.example.com",
        "smtp_port": 587,
    }
    resp = client.patch(f"/api/email/accounts/{account_id}", json=patch_body)

    assert resp.status_code == 401, resp.text


def test_patch_account_missing_required_field_returns_422(
    client: TestClient,
) -> None:
    _as(_USER_A)
    created = client.post("/api/email/accounts", json=_VALID_BODY).json()
    account_id = created["id"]

    # imap_host deliberately empty -> fails ImapIntegrationConfig.min_length=1.
    patch_body = {
        "imap_host": "",
        "imap_port": 993,
        "imap_username": "user@example.com",
        "imap_password": "new-password",
        "smtp_host": "smtp.example.com",
        "smtp_port": 587,
    }
    resp = client.patch(f"/api/email/accounts/{account_id}", json=patch_body)

    assert resp.status_code == 422, resp.text
    body_text = resp.text
    # Field-level error is surfaced (the imap_host field shows up in the body).
    assert "imap_host" in body_text


# ===========================================================================
# gmail-account-oauth-connection-task-response-2-unit-1 (REQ-008)
#
# `DELETE /api/email/accounts/{id}` for a `provider="gmail"` account MUST
# remove both the `email_accounts` row and its linked
# `user_integrations` row (same ownership/404 semantics as `provider="imap"`,
# since the existing `DeleteEmailAccount` use case is provider-agnostic).
# ===========================================================================


def _seed_gmail_account(
    accounts_repo: _FakeEmailAccountRepository,
    integrations_repo: _FakeUserIntegrationRepository,
    *,
    user_id: str,
    account_id: str = "gmail-account-1",
    integration_id: str = "gmail-integration-1",
) -> EmailAccount:
    """Helper: seed a `provider="gmail"` account + its encrypted integration row."""
    integration = UserIntegration(
        id=integration_id,
        user_id=user_id,
        integration_type="gmail",
        config={"email_address": "user@gmail.com", "access_token": "stub"},
    )
    account = EmailAccount(
        id=account_id,
        user_id=user_id,
        user_integration_id=integration_id,
        display_name="user@gmail.com",
        provider="gmail",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    integrations_repo.integrations[integration.id] = integration
    accounts_repo.accounts[account.id] = account
    return account


def test_delete_gmail_account_removes_both_rows(
    client: TestClient,
    accounts_repo: _FakeEmailAccountRepository,
    integrations_repo: _FakeUserIntegrationRepository,
) -> None:
    """REQ-008: DELETE on a `provider="gmail"` account owned by the caller
    removes BOTH the `email_accounts` row and its linked `user_integrations`
    row, and the account is gone from `GET /api/email/accounts`."""
    _as(_USER_A)
    account = _seed_gmail_account(
        accounts_repo, integrations_repo, user_id=_USER_A.id
    )

    delete_resp = client.delete(f"/api/email/accounts/{account.id}")

    assert delete_resp.status_code == 204
    # Both rows are removed.
    assert account.id not in accounts_repo.accounts
    assert account.user_integration_id not in integrations_repo.integrations
    # And the account is gone from the listing.
    list_resp = client.get("/api/email/accounts")
    assert list_resp.status_code == 200
    assert account.id not in [a["id"] for a in list_resp.json()]


def test_delete_gmail_account_repeat_returns_404(
    client: TestClient,
    accounts_repo: _FakeEmailAccountRepository,
    integrations_repo: _FakeUserIntegrationRepository,
) -> None:
    """REQ-008: a second DELETE on the same `provider="gmail"` account
    returns 404 (the account is already gone)."""
    _as(_USER_A)
    account = _seed_gmail_account(
        accounts_repo, integrations_repo, user_id=_USER_A.id
    )

    first = client.delete(f"/api/email/accounts/{account.id}")
    assert first.status_code == 204

    second = client.delete(f"/api/email/accounts/{account.id}")
    assert second.status_code == 404


def test_delete_gmail_account_cross_user_returns_404(
    client: TestClient,
    accounts_repo: _FakeEmailAccountRepository,
    integrations_repo: _FakeUserIntegrationRepository,
) -> None:
    """REQ-008: a different user cannot delete a `provider="gmail"`
    account they do not own — same 404 behavior as `provider="imap"`."""
    _as(_USER_A)
    account = _seed_gmail_account(
        accounts_repo, integrations_repo, user_id=_USER_A.id
    )

    _as(_USER_B)
    resp = client.delete(f"/api/email/accounts/{account.id}")

    assert resp.status_code == 404
    # The rows are untouched — owner still has them.
    assert account.id in accounts_repo.accounts
    assert account.user_integration_id in integrations_repo.integrations
