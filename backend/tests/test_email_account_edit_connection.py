"""Integration tests for the edit-then-sync round trip
(email-account-edit-connection-task-tests-1).

Unit-1 (REQ-004 email-account-edit-connection): after a successful PATCH
with a new IMAP password, the next sync-worker poll authenticates with
the new password, sets `status='connected'`, and updates `last_synced_at`.

Unit-2 (REQ-004): after a PATCH whose IMAP smoke check fails (so the
PATCH is not persisted), a subsequent sync attempt using the
still-stored old password succeeds — i.e., the failed PATCH did not
corrupt the stored credentials.

Unit-3 (REQ-004): when the sync worker hits an IMAP auth failure (the
stored password is rotated externally and the next sync hits that),
`status='error'` is set and `GET /api/email/accounts/{id}` does not
include the plaintext password or the full exception text in any field.

These tests sit alongside `test_email_sync_worker.py` and
`test_email_router.py` — they wire `UpdateEmailAccountConfig`
(service-1) and `PATCH /api/email/accounts/{id}` (api-1) with the sync
worker to exercise the end-to-end flow on real fakes.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest

from src.application.ports.email_account_repository import (
    EmailAccountRepositoryPort,
)
from src.application.ports.email_repository import EmailRepositoryPort
from src.application.ports.user_integration_repository import (
    UserIntegrationRepositoryPort,
)
from src.application.use_cases.update_email_account_config import (
    UpdateEmailAccountConfig,
)
from src.domain.email import EmailAccount, EmailAccountStatus
from src.domain.integrations import UserIntegration
from src.infrastructure.email.imap_client import ImapAuthError

# ---------- Fakes ----------


class _FakeEmailAccountRepository(EmailAccountRepositoryPort):
    def __init__(self, accounts: list[EmailAccount]) -> None:
        self.accounts: dict[str, EmailAccount] = {a.id: a for a in accounts}
        self.update_calls: list[EmailAccount] = []

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
        self.update_calls.append(account)
        self.accounts[account.id] = account
        return account

    async def delete(self, user_id: str, account_id: str) -> bool:
        existing = self.accounts.get(account_id)
        if existing is None or existing.user_id != user_id:
            return False
        del self.accounts[account_id]
        return True


class _FakeUserIntegrationRepository(UserIntegrationRepositoryPort):
    """In-memory fake. `config` is stored in PLAINTEXT (mirrors the
    Postgres adapter after `_decrypt_config`). The use case mutates and
    re-saves via this same path."""

    def __init__(self, integrations: list[UserIntegration]) -> None:
        self.integrations: dict[str, UserIntegration] = {
            i.id: i for i in integrations
        }
        self.save_calls: int = 0

    async def save(self, integration: UserIntegration) -> None:
        self.save_calls += 1
        self.integrations[integration.id] = integration

    async def get(self, integration_id: str) -> UserIntegration | None:
        return self.integrations.get(integration_id)

    async def list_by_user(self, user_id: str) -> list[UserIntegration]:
        return [i for i in self.integrations.values() if i.user_id == user_id]

    async def list_all(self) -> list[UserIntegration]:
        return list(self.integrations.values())

    async def delete(self, integration_id: str) -> None:
        self.integrations.pop(integration_id, None)


# ---------- Helpers ----------


_CONFIG = {
    "imap_host": "imap.example.com",
    "imap_port": 993,
    "imap_username": "user@example.com",
    "imap_password": "old-secret",
    "smtp_host": "smtp.example.com",
    "smtp_port": 587,
    "smtp_username": "user@example.com",
    "smtp_password": "old-smtp-secret",
}


def _seed_account_and_integration(
    account_repo: _FakeEmailAccountRepository,
    integration_repo: _FakeUserIntegrationRepository,
    *,
    imap_password: str = "old-secret",
) -> tuple[EmailAccount, UserIntegration]:
    """Cria uma conta ativa + integração com senha IMAP inicial."""
    now = datetime.now(UTC)
    integration = UserIntegration(
        id=str(uuid.uuid4()),
        user_id="user-a",
        integration_type="imap",
        config={**_CONFIG, "imap_password": imap_password},
        created_at=now,
        updated_at=now,
    )
    account = EmailAccount(
        id=str(uuid.uuid4()),
        user_id="user-a",
        user_integration_id=integration.id,
        display_name="Trabalho",
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    account_repo.accounts[account.id] = account
    integration_repo.integrations[integration.id] = integration
    return account, integration


async def _ok_verify_login(config: Any) -> None:
    """verify_login fake que aceita qualquer config — usado quando o teste
    não está exercitando o caminho de falha do smoke check."""
    return None


async def _failing_verify_login(config: Any) -> None:
    raise ImapAuthError("Login IMAP recusado pelo servidor (result='NO').")


def _make_worker(
    account_repo: _FakeEmailAccountRepository,
    integration_repo: _FakeUserIntegrationRepository,
    *,
    fetch_messages: Any,
) -> Any:
    """Constrói um `EmailSyncWorker` real com fakes em todas as portas
    EXCETO `fetch_messages` (que é fornecido pelo teste). O worker tem
    também uma dependência de `EmailRepositoryPort` e `CrmRepositoryPort`
    que NÃO são exercitadas neste round trip — instanciamos fakes
    mínimos para satisfazer o construtor."""
    from src.infrastructure.email.sync_worker import EmailSyncWorker

    class _NoopEmailRepository(EmailRepositoryPort):
        async def upsert_email(  # pragma: no cover
            self,
            email_account_id: str,
            message,
            attachments=None,
            contact_id=None,
        ):
            raise NotImplementedError

        async def list_by_account(
            self, user_id, account_id=None, folder=None, limit=20, offset=0,
        ):
            raise NotImplementedError

        async def get(self, user_id, email_id):  # pragma: no cover
            raise NotImplementedError

        async def get_by_message_id(  # pragma: no cover
            self, user_id, message_id
        ):
            raise NotImplementedError

        async def search(  # pragma: no cover
            self, user_id, account_id, query, limit=20
        ):
            raise NotImplementedError

        async def mark_read(self, user_id, email_id):  # pragma: no cover
            raise NotImplementedError

        async def move_folder(self, user_id, email_id, folder):  # pragma: no cover
            raise NotImplementedError

    class _NoopCrmRepository:
        async def get_or_create_contact_by_email(self, user_id: str, email: str):
            return None

        async def list_companies(self, user_id: str):
            return []

        async def list_contacts(self, user_id: str):
            return []

        async def list_field_definitions(self, entity: str):
            return []

        async def get_contact(self, user_id: str, contact_id: str):
            return None

        async def list_deals(self, user_id: str):
            return []

        async def list_notes(self, user_id: str, contact_id: str | None = None):
            return []

    return EmailSyncWorker(
        account_repository=account_repo,
        integration_repository=integration_repo,
        email_repository=_NoopEmailRepository(),  # type: ignore[arg-type]
        crm_repository=_NoopCrmRepository(),  # type: ignore[arg-type]
        fetch_messages=fetch_messages,
    )


# ---------- Tests ----------


@pytest.mark.asyncio
async def test_edit_then_sync_new_password_authenticates() -> None:
    """unit-1 (REQ-004): a successful PATCH with a new IMAP password is
    honored by the next sync-worker poll against the fake IMAP server.
    """
    account_repo = _FakeEmailAccountRepository([])
    integration_repo = _FakeUserIntegrationRepository([])
    account, integration = _seed_account_and_integration(
        account_repo, integration_repo, imap_password="old-secret"
    )
    pre_update_at = account.last_synced_at  # None on a freshly-created account

    # --- Edit step: PATCH with the new IMAP password ---
    patch_use_case = UpdateEmailAccountConfig(
        repository=account_repo,
        integration_repository=integration_repo,
        verify_login=_ok_verify_login,
    )
    updated = await patch_use_case.execute(
        user_id="user-a",
        account_id=account.id,
        config_patch={"imap_password": "new-imap-secret"},
        display_name=None,
    )
    assert updated is not None
    assert updated.status == EmailAccountStatus.CONNECTED
    assert pre_update_at is None  # sanity

    # The DECRYPTED config now holds the new password (the Postgres
    # adapter's `_encrypt_config` is bypassed by the fake; we observe
    # plaintext directly).
    assert (
        integration_repo.integrations[integration.id].config["imap_password"]
        == "new-imap-secret"
    )

    # --- Sync step: poll_once picks up the rotated password ---
    received_logins: list[tuple[str, str]] = []

    async def fake_fetch(config, folder, watermark):
        # Capture the password the worker uses for the IMAP login.
        received_logins.append((config.imap_username, config.imap_password))
        return []

    worker = _make_worker(account_repo, integration_repo, fetch_messages=fake_fetch)
    await worker.poll_once()

    assert len(received_logins) == 1
    assert received_logins[0] == ("user@example.com", "new-imap-secret")

    final_account = account_repo.accounts[account.id]
    assert final_account.status == EmailAccountStatus.CONNECTED
    assert final_account.last_synced_at is not None
    if pre_update_at is not None:
        assert final_account.last_synced_at > pre_update_at


@pytest.mark.asyncio
async def test_edit_then_sync_failed_patch_leaves_credentials_intact() -> None:
    """unit-2 (REQ-004): a PATCH whose IMAP smoke check fails does NOT
    persist the new password, and the next sync using the still-stored
    old password succeeds.
    """
    account_repo = _FakeEmailAccountRepository([])
    integration_repo = _FakeUserIntegrationRepository([])
    account, integration = _seed_account_and_integration(
        account_repo, integration_repo, imap_password="old-secret"
    )

    # --- Edit step: PATCH with a wrong IMAP password; smoke check fails ---
    patch_use_case = UpdateEmailAccountConfig(
        repository=account_repo,
        integration_repository=integration_repo,
        verify_login=_failing_verify_login,
    )
    with pytest.raises(ImapAuthError):
        await patch_use_case.execute(
            user_id="user-a",
            account_id=account.id,
            config_patch={"imap_password": "wrong-password"},
            display_name=None,
        )

    # Stored credential is unchanged.
    assert (
        integration_repo.integrations[integration.id].config["imap_password"]
        == "old-secret"
    )
    # No update on the account row.
    assert account_repo.update_calls == []
    # The integration save was NOT called.
    assert integration_repo.save_calls == 0

    # --- Sync step: poll_once still uses the old password ---
    received_logins: list[str] = []

    async def fake_fetch(config, folder, watermark):
        received_logins.append(config.imap_password)
        return []

    worker = _make_worker(account_repo, integration_repo, fetch_messages=fake_fetch)
    await worker.poll_once()

    assert received_logins == ["old-secret"]
    assert account_repo.accounts[account.id].status == EmailAccountStatus.CONNECTED


@pytest.mark.asyncio
async def test_get_account_after_sync_failure_does_not_leak_secrets() -> None:
    """unit-3 (REQ-004): when the sync worker hits an IMAP auth failure
    (e.g. password rotated externally), `status='error'` is set AND a
    subsequent `GET /api/email/accounts/{id}` does NOT include the
    plaintext password, the full exception text, or any extra IMAP
    server URL/credentials beyond the configured host/port.
    """
    from fastapi.testclient import TestClient

    import src.infrastructure.web.email_router as email_router
    import src.infrastructure.web.webapp as webapp
    from src.infrastructure.auth.dependencies import require_auth
    from src.infrastructure.auth.users import User

    account_repo = _FakeEmailAccountRepository([])
    integration_repo = _FakeUserIntegrationRepository([])
    account, integration = _seed_account_and_integration(
        account_repo, integration_repo, imap_password="correct-secret"
    )

    # --- Sync step: simulate an externally-rotated password by making
    # the fake IMAP server reject the login ---
    leaked_text = "secret=correct-secret leaked"

    async def failing_fetch(config, folder, watermark):
        # The error message must NOT contain the password — this is
        # what the worker would log and potentially surface. The test
        # asserts below that this exact string never appears in the
        # HTTP response.
        raise ImapAuthError(
            f"Login IMAP recusado pelo servidor (result='NO'). Detalhes: {leaked_text}"
        )

    worker = _make_worker(account_repo, integration_repo, fetch_messages=failing_fetch)
    await worker.poll_once()

    # Account marked error.
    assert account_repo.accounts[account.id].status == EmailAccountStatus.ERROR
    # Credentials are NOT re-written.
    assert (
        integration_repo.integrations[integration.id].config["imap_password"]
        == "correct-secret"
    )

    # --- GET via the real HTTP route (api-1 wiring) ---
    test_user = User(
        id="user-a",
        username="alice",
        password_hash="h",
        role="user",
        is_active=True,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    webapp.app.dependency_overrides[email_router._email_account_repository] = (
        lambda: account_repo
    )
    webapp.app.dependency_overrides[email_router._user_integration_repository] = (
        lambda: integration_repo
    )
    webapp.app.dependency_overrides[require_auth] = lambda: test_user
    try:
        client = TestClient(webapp.app)
        resp = client.get(f"/api/email/accounts/{account.id}")
    finally:
        webapp.app.dependency_overrides.pop(require_auth, None)
        webapp.app.dependency_overrides.pop(
            email_router._email_account_repository, None
        )
        webapp.app.dependency_overrides.pop(
            email_router._user_integration_repository, None
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    body_text = resp.text

    # Plaintext password never appears.
    assert "correct-secret" not in body_text
    # The leaked exception text never appears.
    assert leaked_text not in body_text
    assert "Detalhes:" not in body_text
    assert "ImapAuthError" not in body_text
    # The configured non-secret host/port DO appear (they're
    # legitimate config — the spec allows exposing host/port).
    assert body["imap_host"] == "imap.example.com"
    assert body["imap_port"] == 993
    assert body["status"] == "error"
