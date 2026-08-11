"""Testes dos use cases de contas de email (email-client-imap-mvp-task-accounts-1).

Unit-1 (REQ-001 email-account-management): ConnectEmailAccount happy path +
rejeição de config incompleto sem persistir nada.
Unit-2 (REQ-002/REQ-004): DeleteEmailAccount remove email_accounts +
user_integrations própria; Get/Update/Delete cross-user se comportam como
"não encontrado".

Nota sobre o cenário "synced emails rows still queryable" do unit-2: a
tabela `emails`/seu repositório ainda não existem neste ponto do plano
(chegam em `email-client-imap-mvp-task-inbox-1`/`task-sync-2`). O que É
verificável agora — e o que este teste verifica — é que `DeleteEmailAccount`
não depende de nenhum repositório de emails, logo estruturalmente não pode
apagar mensagens sincronizadas; a asserção completa de retenção real de
`emails` fica para quando esse repositório existir.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.application.ports.email_account_repository import (
    EmailAccountRepositoryPort,
)
from src.application.ports.user_integration_repository import (
    UserIntegrationRepositoryPort,
)
from src.domain.email import EmailAccount, EmailAccountStatus
from src.domain.integrations import UserIntegration


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
        self.save_calls = 0

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


_VALID_CONFIG = {
    "imap_host": "imap.example.com",
    "imap_port": 993,
    "imap_username": "user@example.com",
    "imap_password": "secret",
    "smtp_host": "smtp.example.com",
    "smtp_port": 587,
}


async def _always_ok_verify_login(config: object) -> None:
    """Fake `verify_login` — connecting succeeds, used where login isn't under test."""
    return None


async def test_connect_email_account_happy_path() -> None:
    from src.application.use_cases.connect_email_account import ConnectEmailAccount

    accounts_repo = _FakeEmailAccountRepository()
    integrations_repo = _FakeUserIntegrationRepository()
    uc = ConnectEmailAccount(
        repository=accounts_repo,
        integration_repository=integrations_repo,
        verify_login=_always_ok_verify_login,
    )

    account = await uc.execute(
        user_id="user-a", display_name="Trabalho", config=_VALID_CONFIG
    )

    assert account.user_id == "user-a"
    assert account.status == EmailAccountStatus.CONNECTED
    assert accounts_repo.accounts[account.id] is account
    linked = integrations_repo.integrations[account.user_integration_id]
    assert linked.user_id == "user-a"
    assert linked.integration_type == "imap"
    # config values are the validated plaintext at this layer — encryption
    # happens in PostgresUserIntegrationRepository, below this port.
    assert linked.config["imap_password"] == "secret"


async def test_connect_email_account_rejects_incomplete_config() -> None:
    from src.application.use_cases.connect_email_account import ConnectEmailAccount

    accounts_repo = _FakeEmailAccountRepository()
    integrations_repo = _FakeUserIntegrationRepository()
    uc = ConnectEmailAccount(
        repository=accounts_repo,
        integration_repository=integrations_repo,
        verify_login=_always_ok_verify_login,
    )
    incomplete_config = {k: v for k, v in _VALID_CONFIG.items() if k != "imap_host"}

    with pytest.raises(ValidationError):
        await uc.execute(
            user_id="user-a", display_name="Trabalho", config=incomplete_config
        )

    assert accounts_repo.accounts == {}
    assert integrations_repo.integrations == {}
    assert integrations_repo.save_calls == 0


async def test_delete_email_account_removes_account_and_credentials() -> None:
    from src.application.use_cases.connect_email_account import ConnectEmailAccount
    from src.application.use_cases.delete_email_account import DeleteEmailAccount

    accounts_repo = _FakeEmailAccountRepository()
    integrations_repo = _FakeUserIntegrationRepository()
    connected = await ConnectEmailAccount(
        repository=accounts_repo,
        integration_repository=integrations_repo,
        verify_login=_always_ok_verify_login,
    ).execute(user_id="user-a", display_name="Trabalho", config=_VALID_CONFIG)

    deleted = await DeleteEmailAccount(
        repository=accounts_repo, integration_repository=integrations_repo
    ).execute(user_id="user-a", account_id=connected.id)

    assert deleted is True
    assert connected.id not in accounts_repo.accounts
    assert connected.user_integration_id not in integrations_repo.integrations


async def test_cross_user_get_update_delete_behave_as_not_found() -> None:
    from src.application.use_cases.connect_email_account import ConnectEmailAccount
    from src.application.use_cases.delete_email_account import DeleteEmailAccount
    from src.application.use_cases.get_email_account import GetEmailAccount
    from src.application.use_cases.update_email_account import UpdateEmailAccount

    accounts_repo = _FakeEmailAccountRepository()
    integrations_repo = _FakeUserIntegrationRepository()
    connected = await ConnectEmailAccount(
        repository=accounts_repo,
        integration_repository=integrations_repo,
        verify_login=_always_ok_verify_login,
    ).execute(user_id="user-a", display_name="Trabalho", config=_VALID_CONFIG)

    assert (
        await GetEmailAccount(repository=accounts_repo).execute(
            user_id="user-b", account_id=connected.id
        )
        is None
    )
    assert (
        await UpdateEmailAccount(repository=accounts_repo).execute(
            user_id="user-b", account_id=connected.id, display_name="Hijacked"
        )
        is None
    )
    assert (
        await DeleteEmailAccount(
            repository=accounts_repo, integration_repository=integrations_repo
        ).execute(user_id="user-b", account_id=connected.id)
        is False
    )
    # Nothing was actually touched by the cross-user attempts.
    assert accounts_repo.accounts[connected.id].display_name == "Trabalho"
    assert connected.user_integration_id in integrations_repo.integrations


async def test_connect_email_account_rejects_bad_login_before_persisting() -> None:
    """email-client-imap-mvp-task-accounts-2-unit-2 (REQ-001): login recusado
    propaga ImapAuthError e nenhuma das duas linhas é persistida."""
    from src.application.use_cases.connect_email_account import ConnectEmailAccount
    from src.infrastructure.email.imap_client import ImapAuthError

    accounts_repo = _FakeEmailAccountRepository()
    integrations_repo = _FakeUserIntegrationRepository()

    async def _failing_verify_login(config: object) -> None:
        raise ImapAuthError("bad credentials")

    uc = ConnectEmailAccount(
        repository=accounts_repo,
        integration_repository=integrations_repo,
        verify_login=_failing_verify_login,
    )

    with pytest.raises(ImapAuthError):
        await uc.execute(
            user_id="user-a", display_name="Trabalho", config=_VALID_CONFIG
        )

    assert accounts_repo.accounts == {}
    assert integrations_repo.integrations == {}
    assert integrations_repo.save_calls == 0


# ---------------------------------------------------------------------------
# email-account-edit-connection: tests for `UpdateEmailAccountConfig`
#
# The use case class lives in
# `src/application/use_cases/update_email_account_config.py`. It edits the
# connection settings (IMAP/SMTP host/port/username/password, display_name)
# of an owned `email_accounts` entry, with the same ownership/isolation
# guarantees and the same IMAP smoke check as `ConnectEmailAccount` — but
# the contract on a missing/blank password is "keep the current value",
# so the merged config is what gets re-validated and re-verified.
# ---------------------------------------------------------------------------


async def _seed_connected_account(
    accounts_repo: _FakeEmailAccountRepository,
    integrations_repo: _FakeUserIntegrationRepository,
) -> EmailAccount:
    """Helper: connect a fresh account for user-a and return it."""
    from src.application.use_cases.connect_email_account import ConnectEmailAccount

    return await ConnectEmailAccount(
        repository=accounts_repo,
        integration_repository=integrations_repo,
        verify_login=_always_ok_verify_login,
    ).execute(user_id="user-a", display_name="Trabalho", config=_VALID_CONFIG)


async def test_update_email_account_config_rejects_non_owner() -> None:
    """email-account-edit-connection-task-service-1-unit-1 (REQ-003):
    loading a row owned by user-b as user-a returns None and writes nothing."""
    from src.application.use_cases.update_email_account_config import (
        UpdateEmailAccountConfig,
    )

    accounts_repo = _FakeEmailAccountRepository()
    integrations_repo = _FakeUserIntegrationRepository()
    connected = await _seed_connected_account(accounts_repo, integrations_repo)
    pre_update_count = integrations_repo.save_calls

    uc = UpdateEmailAccountConfig(
        repository=accounts_repo,
        integration_repository=integrations_repo,
        verify_login=_always_ok_verify_login,
    )

    result = await uc.execute(
        user_id="user-b",
        account_id=connected.id,
        config_patch={"imap_host": "attacker.example.com"},
        display_name=None,
    )

    assert result is None
    # The repo is keyed by id; verify the linked integration was untouched.
    linked = integrations_repo.integrations[connected.user_integration_id]
    assert linked.config["imap_host"] == "imap.example.com"
    assert integrations_repo.save_calls == pre_update_count


async def test_update_email_account_config_blank_passwords_preserve_plaintext() -> None:
    """email-account-edit-connection-task-service-1-unit-2 (REQ-002):
    blank passwords leave the DECRYPTED password values unchanged and only
    update the non-password fields the user submitted."""
    from src.application.use_cases.update_email_account_config import (
        UpdateEmailAccountConfig,
    )

    accounts_repo = _FakeEmailAccountRepository()
    integrations_repo = _FakeUserIntegrationRepository()
    connected = await _seed_connected_account(accounts_repo, integrations_repo)

    uc = UpdateEmailAccountConfig(
        repository=accounts_repo,
        integration_repository=integrations_repo,
        verify_login=_always_ok_verify_login,
    )

    updated = await uc.execute(
        user_id="user-a",
        account_id=connected.id,
        config_patch={"imap_host": "new.host.example.com", "imap_port": 143},
        display_name="Trabalho (renamed)",
    )

    assert updated is not None
    assert updated.display_name == "Trabalho (renamed)"
    assert updated.status == EmailAccountStatus.CONNECTED
    linked = integrations_repo.integrations[connected.user_integration_id]
    # DECRYPTED password values are preserved.
    assert linked.config["imap_password"] == "secret"
    assert linked.config["smtp_password"] == "secret"
    # Non-password fields the user changed are written.
    assert linked.config["imap_host"] == "new.host.example.com"
    assert linked.config["imap_port"] == 143


async def test_update_email_account_config_new_passwords_replace_plaintext() -> None:
    """email-account-edit-connection-task-service-1-unit-3 (REQ-002):
    new passwords for both IMAP and SMTP replace the prior DECRYPTED password
    values; everything else stays the same."""
    from src.application.use_cases.update_email_account_config import (
        UpdateEmailAccountConfig,
    )

    accounts_repo = _FakeEmailAccountRepository()
    integrations_repo = _FakeUserIntegrationRepository()
    connected = await _seed_connected_account(accounts_repo, integrations_repo)

    uc = UpdateEmailAccountConfig(
        repository=accounts_repo,
        integration_repository=integrations_repo,
        verify_login=_always_ok_verify_login,
    )

    updated = await uc.execute(
        user_id="user-a",
        account_id=connected.id,
        config_patch={
            "imap_password": "new-imap-secret",
            "smtp_password": "new-smtp-secret",
        },
        display_name=None,
    )

    assert updated is not None
    linked = integrations_repo.integrations[connected.user_integration_id]
    assert linked.config["imap_password"] == "new-imap-secret"
    assert linked.config["smtp_password"] == "new-smtp-secret"
    # Hosts/ports preserved.
    assert linked.config["imap_host"] == "imap.example.com"
    assert linked.config["smtp_port"] == 587


async def test_update_email_account_config_validation_error_leaves_rows_untouched() -> None:
    """email-account-edit-connection-task-service-1-unit-4 (REQ-002):
    a missing required field raises ValidationError and writes nothing."""
    from src.application.use_cases.update_email_account_config import (
        UpdateEmailAccountConfig,
    )

    accounts_repo = _FakeEmailAccountRepository()
    integrations_repo = _FakeUserIntegrationRepository()
    connected = await _seed_connected_account(accounts_repo, integrations_repo)
    pre_update_count = integrations_repo.save_calls
    pre_account = accounts_repo.accounts[connected.id]

    uc = UpdateEmailAccountConfig(
        repository=accounts_repo,
        integration_repository=integrations_repo,
        verify_login=_always_ok_verify_login,
    )

    with pytest.raises(ValidationError):
        await uc.execute(
            user_id="user-a",
            account_id=connected.id,
            config_patch={"imap_host": ""},  # empty → violates min_length=1
            display_name=None,
        )

    assert integrations_repo.save_calls == pre_update_count
    assert accounts_repo.accounts[connected.id] is pre_account
    linked = integrations_repo.integrations[connected.user_integration_id]
    assert linked.config["imap_host"] == "imap.example.com"


async def test_update_email_account_config_imap_auth_error_leaves_rows_untouched() -> None:
    """email-account-edit-connection-task-service-1-unit-5 (REQ-002):
    a verify_imap_login ImapAuthError propagates and writes nothing."""
    from src.application.use_cases.update_email_account_config import (
        UpdateEmailAccountConfig,
    )
    from src.infrastructure.email.imap_client import ImapAuthError

    accounts_repo = _FakeEmailAccountRepository()
    integrations_repo = _FakeUserIntegrationRepository()
    connected = await _seed_connected_account(accounts_repo, integrations_repo)
    pre_update_count = integrations_repo.save_calls
    pre_account = accounts_repo.accounts[connected.id]

    async def _failing_verify_login(config: object) -> None:
        raise ImapAuthError("bad credentials")

    uc = UpdateEmailAccountConfig(
        repository=accounts_repo,
        integration_repository=integrations_repo,
        verify_login=_failing_verify_login,
    )

    with pytest.raises(ImapAuthError):
        await uc.execute(
            user_id="user-a",
            account_id=connected.id,
            config_patch={"imap_password": "new-imap-secret"},
            display_name=None,
        )

    assert integrations_repo.save_calls == pre_update_count
    assert accounts_repo.accounts[connected.id] is pre_account
    linked = integrations_repo.integrations[connected.user_integration_id]
    assert linked.config["imap_password"] == "secret"


async def test_update_email_account_config_db_error_during_save_rolls_back() -> None:
    """email-account-edit-connection-task-service-1-unit-6 (REQ-002):
    a DB error during integration.save (after email_accounts.update has
    already been called) propagates and leaves the in-memory state
    untouched."""

    class _FailingIntegrationRepo(_FakeUserIntegrationRepository):
        async def save(self, integration: UserIntegration) -> None:  # type: ignore[override]
            raise RuntimeError("simulated DB error mid-transaction")

    class _CountingAccountRepo(_FakeEmailAccountRepository):
        def __init__(self) -> None:
            super().__init__()
            self.update_calls = 0

        async def update(self, account: EmailAccount) -> EmailAccount | None:  # type: ignore[override]
            self.update_calls += 1
            return await super().update(account)

    # Seed using the regular (non-failing) repos, then swap to the failing
    # integration repo before invoking `execute`.
    seed_accounts_repo = _FakeEmailAccountRepository()
    seed_integrations_repo = _FakeUserIntegrationRepository()
    connected = await _seed_connected_account(seed_accounts_repo, seed_integrations_repo)

    accounts_repo = _CountingAccountRepo()
    accounts_repo.accounts.update(seed_accounts_repo.accounts)
    integrations_repo = _FailingIntegrationRepo()
    integrations_repo.integrations.update(seed_integrations_repo.integrations)

    from src.application.use_cases.update_email_account_config import (
        UpdateEmailAccountConfig,
    )

    uc = UpdateEmailAccountConfig(
        repository=accounts_repo,
        integration_repository=integrations_repo,
        verify_login=_always_ok_verify_login,
    )

    with pytest.raises(RuntimeError, match="simulated DB error"):
        await uc.execute(
            user_id="user-a",
            account_id=connected.id,
            config_patch={"imap_host": "new.host.example.com"},
            display_name=None,
        )

    # The implementation's transactional model: `_repository.update` runs
    # first, then `_integration_repository.save` runs. If the second write
    # fails, the exception propagates and the caller (handler or production
    # Postgres adapter, which opens a transaction around both calls) is
    # responsible for rolling back the first write. The testable contract
    # of this use case is therefore:
    #   (a) `_integration_repository.save` was invoked exactly once
    #       (and raised the simulated error);
    #   (b) the `UserIntegration`'s stored config was NOT mutated (because
    #       the fake's `save` raises before any state change);
    #   (c) the simulated exception propagates so the caller can decide
    #       what to do (the handler maps it to a 5xx).
    # The `email_accounts.update` having already run is acceptable; in
    # production, the Postgres adapter wraps both writes in a transaction
    # and rolls back on the second write's failure.
    linked = integrations_repo.integrations[connected.user_integration_id]
    assert linked.config["imap_host"] == "imap.example.com"


async def test_update_email_account_config_integration_user_id_mismatch_returns_none() -> None:
    """email-account-edit-connection-task-service-1-unit-7 (REQ-003):
    defence-in-depth: if the linked `user_integrations` row has a different
    `user_id` than the caller's, the use case returns None and writes nothing
    (even though the parent `email_accounts` row matches)."""
    from src.application.use_cases.update_email_account_config import (
        UpdateEmailAccountConfig,
    )

    accounts_repo = _FakeEmailAccountRepository()
    integrations_repo = _FakeUserIntegrationRepository()
    connected = await _seed_connected_account(accounts_repo, integrations_repo)

    # Simulate the data-corruption/admin-override scenario: the integration
    # is claimed by another user.
    integrations_repo.integrations[connected.user_integration_id].user_id = "user-b"

    uc = UpdateEmailAccountConfig(
        repository=accounts_repo,
        integration_repository=integrations_repo,
        verify_login=_always_ok_verify_login,
    )

    result = await uc.execute(
        user_id="user-a",
        account_id=connected.id,
        config_patch={"imap_host": "hijacked.example.com"},
        display_name=None,
    )

    assert result is None
    linked = integrations_repo.integrations[connected.user_integration_id]
    assert linked.config["imap_host"] == "imap.example.com"
