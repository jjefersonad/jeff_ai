"""Testes de `EmailSyncWorker.poll_once` (email-client-imap-mvp-task-sync-3).

Unit-1 (REQ-003/REQ-005 email-account-management): dado um mix de contas
ativas/inativas, `poll_once` só busca/persiste para as ativas; dado um erro
de autenticação IMAP numa conta, `status` vira "error" e a credencial
(`user_integrations`) nunca é reescrita.

Cobre também a associação de contato (`email-client-imap-mvp-task-inbox-4`
REQ-006): o sync worker resolve `Contact` por `from_address` (case-
insensitive) e passa o `contact_id` para `upsert_email`. Sem match,
`contact_id=None` e nenhum erro é levantado.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from crm_repository_fakes import CrmRepositoryPortExtensions

from src.application.ports.crm_repository import CrmRepositoryPort
from src.application.ports.email_account_repository import (
    EmailAccountRepositoryPort,
)
from src.application.ports.email_repository import EmailRepositoryPort
from src.application.ports.user_integration_repository import (
    UserIntegrationRepositoryPort,
)
from src.domain.crm import (
    Company,
    Contact,
    Deal,
    DealStage,
    FieldDefinition,
    FieldEntity,
    Note,
)
from src.domain.email import Email, EmailAccount, EmailAccountStatus, ParsedMessage
from src.domain.integrations import UserIntegration
from src.infrastructure.email.imap_client import ImapAuthError
from src.infrastructure.email.sync_worker import EmailSyncWorker


class _FakeEmailAccountRepository(EmailAccountRepositoryPort):
    def __init__(self, accounts: list[EmailAccount]) -> None:
        self.accounts = {a.id: a for a in accounts}
        self.update_calls: list[EmailAccount] = []

    async def create(self, account: EmailAccount) -> EmailAccount:
        raise NotImplementedError

    async def get(self, user_id: str, account_id: str) -> EmailAccount | None:
        raise NotImplementedError

    async def list_by_user(self, user_id: str) -> list[EmailAccount]:
        raise NotImplementedError

    async def list_all(self) -> list[EmailAccount]:
        return list(self.accounts.values())

    async def update(self, account: EmailAccount) -> EmailAccount | None:
        self.update_calls.append(account)
        self.accounts[account.id] = account
        return account

    async def delete(self, user_id: str, account_id: str) -> bool:
        raise NotImplementedError


class _FakeUserIntegrationRepository(UserIntegrationRepositoryPort):
    def __init__(self, integrations: list[UserIntegration]) -> None:
        self.integrations = {i.id: i for i in integrations}
        self.save_calls = 0

    async def save(self, integration: UserIntegration) -> None:
        self.save_calls += 1
        self.integrations[integration.id] = integration

    async def get(self, integration_id: str) -> UserIntegration | None:
        return self.integrations.get(integration_id)

    async def list_by_user(self, user_id: str) -> list[UserIntegration]:
        raise NotImplementedError

    async def list_all(self) -> list[UserIntegration]:
        raise NotImplementedError

    async def delete(self, integration_id: str) -> None:
        raise NotImplementedError


class _FakeEmailRepository(EmailRepositoryPort):
    def __init__(self) -> None:
        self.upsert_calls: list[tuple[str, ParsedMessage, str | None]] = []

    async def upsert_email(
        self, email_account_id, message, attachments=None, contact_id=None
    ) -> Email:
        self.upsert_calls.append((email_account_id, message, contact_id))
        return Email(
            id=str(uuid.uuid4()),
            email_account_id=email_account_id,
            message_id=message.message_id,
            thread_id=None,
            folder=message.folder,
            from_address=message.from_address,
            from_name=message.from_name,
            to_addresses=message.to_addresses,
            cc_addresses=[],
            bcc_addresses=[],
            subject=message.subject,
            body_html=message.body_html,
            body_text=message.body_text,
            is_read=False,
            is_starred=False,
            has_attachments=False,
            contact_id=contact_id,
            received_at=message.received_at,
        )

    async def list_by_account(self, user_id, account_id, folder, limit, offset):
        raise NotImplementedError

    async def get(self, user_id, email_id):
        raise NotImplementedError

    async def get_by_message_id(self, user_id, message_id):
        raise NotImplementedError

    async def search(self, user_id, account_id, query, limit):
        raise NotImplementedError

    async def mark_read(self, user_id, email_id):
        raise NotImplementedError

    async def move_folder(self, user_id, email_id, folder):
        raise NotImplementedError


class _FakeCrmRepository(CrmRepositoryPortExtensions, CrmRepositoryPort):
    def __init__(self, contacts: list[Contact] | None = None) -> None:
        self.contacts: dict[str, Contact] = {c.id: c for c in (contacts or [])}
        self.get_by_email_calls: list[tuple[str, str]] = []

    async def create_company(self, company: Company) -> Company:
        raise NotImplementedError

    async def get_company(self, user_id: str, company_id: str) -> Company | None:
        return None

    async def list_companies(
        self,
        user_id: str,
        *,
        query: str | None = None,
        include_archived: bool = False,
    ) -> list[Company]:
        return []

    async def update_company(self, company: Company) -> Company | None:
        return None

    async def archive_company(self, user_id: str, company_id: str) -> Company | None:
        return None

    async def create_contact(self, contact: Contact) -> Contact:
        self.contacts[contact.id] = contact
        return contact

    async def get_contact(self, user_id: str, contact_id: str) -> Contact | None:
        contact = self.contacts.get(contact_id)
        if contact is None or contact.user_id != user_id:
            return None
        return contact

    async def get_contact_by_email(
        self, user_id: str, email: str
    ) -> Contact | None:
        self.get_by_email_calls.append((user_id, email))
        target = email.strip().lower()
        for contact in self.contacts.values():
            if contact.user_id != user_id:
                continue
            if contact.email and contact.email.strip().lower() == target:
                return contact
        return None

    async def list_contacts(
        self,
        user_id: str,
        *,
        query: str | None = None,
        company_id: str | None = None,
        include_archived: bool = False,
    ) -> list[Contact]:
        return []

    async def update_contact(self, contact: Contact) -> Contact | None:
        return None

    async def archive_contact(self, user_id: str, contact_id: str) -> Contact | None:
        return None

    async def create_deal(self, deal: Deal) -> Deal:
        raise NotImplementedError

    async def get_deal(self, user_id: str, deal_id: str) -> Deal | None:
        return None

    async def list_deals(
        self,
        user_id: str,
        *,
        stage: DealStage | None = None,
        include_archived: bool = False,
    ) -> list[Deal]:
        return []

    async def update_deal(self, deal: Deal) -> Deal | None:
        return None

    async def archive_deal(self, user_id: str, deal_id: str) -> Deal | None:
        return None

    async def move_deal(
        self, user_id: str, deal_id: str, stage: DealStage
    ) -> Deal | None:
        return None

    async def create_note(self, note: Note) -> Note:
        raise NotImplementedError

    async def list_notes_for_contact(
        self,
        user_id: str,
        contact_id: str,
        *,
        include_archived: bool = False,
    ) -> list[Note]:
        return []

    async def list_notes_for_company(
        self,
        user_id: str,
        company_id: str,
        *,
        include_archived: bool = False,
    ) -> list[Note]:
        return []

    async def list_notes_for_deal(
        self,
        user_id: str,
        deal_id: str,
        *,
        include_archived: bool = False,
    ) -> list[Note]:
        return []

    async def create_field_definition(
        self, definition: FieldDefinition
    ) -> FieldDefinition:
        raise NotImplementedError

    async def list_field_definitions(
        self,
        user_id: str,
        *,
        entity: FieldEntity | None = None,
    ) -> list[FieldDefinition]:
        return []

    async def update_field_definition_label(
        self, user_id: str, definition_id: str, label: str
    ) -> FieldDefinition | None:
        return None


_CONFIG = {
    "imap_host": "imap.example.com",
    "imap_port": 993,
    "imap_username": "user@example.com",
    "imap_password": "secret",
    "smtp_host": "smtp.example.com",
    "smtp_port": 587,
}


def _account(*, is_active: bool, integration_id: str) -> EmailAccount:
    now = datetime.now(UTC)
    return EmailAccount(
        id=str(uuid.uuid4()),
        user_id="user-a",
        user_integration_id=integration_id,
        display_name="Trabalho",
        is_active=is_active,
        created_at=now,
        updated_at=now,
    )


def _integration() -> UserIntegration:
    now = datetime.now(UTC)
    return UserIntegration(
        id=str(uuid.uuid4()),
        user_id="user-a",
        integration_type="imap",
        config=dict(_CONFIG),
        created_at=now,
        updated_at=now,
    )


def _message(uid: str = "1", from_address: str = "sender@example.com") -> ParsedMessage:
    return ParsedMessage(
        uid=uid,
        message_id=f"msg-{uid}",
        folder="INBOX",
        from_address=from_address,
        from_name="Sender",
        to_addresses=["user@example.com"],
        subject="Hello",
        body_html=None,
        body_text="hi",
        received_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_poll_once_skips_inactive_accounts() -> None:
    active_integration = _integration()
    inactive_integration = _integration()
    active_account = _account(is_active=True, integration_id=active_integration.id)
    inactive_account = _account(is_active=False, integration_id=inactive_integration.id)

    account_repo = _FakeEmailAccountRepository([active_account, inactive_account])
    integration_repo = _FakeUserIntegrationRepository(
        [active_integration, inactive_integration]
    )
    email_repo = _FakeEmailRepository()
    crm_repo = _FakeCrmRepository()

    fetch_calls: list[tuple[str, str]] = []

    async def fake_fetch(config, folder, watermark):
        fetch_calls.append((config.imap_username, folder))
        return [_message()]

    worker = EmailSyncWorker(
        account_repository=account_repo,
        integration_repository=integration_repo,
        email_repository=email_repo,
        crm_repository=crm_repo,
        fetch_messages=fake_fetch,
    )

    await worker.poll_once()

    assert len(fetch_calls) == 1
    assert len(email_repo.upsert_calls) == 1
    assert email_repo.upsert_calls[0][0] == active_account.id
    assert account_repo.accounts[active_account.id].status == EmailAccountStatus.CONNECTED
    assert account_repo.accounts[active_account.id].last_synced_at is not None
    assert account_repo.accounts[inactive_account.id].status == EmailAccountStatus.CONNECTED
    assert account_repo.accounts[inactive_account.id].last_synced_at is None


@pytest.mark.asyncio
async def test_poll_once_marks_error_on_auth_failure_without_touching_credentials() -> None:
    integration = _integration()
    account = _account(is_active=True, integration_id=integration.id)

    account_repo = _FakeEmailAccountRepository([account])
    integration_repo = _FakeUserIntegrationRepository([integration])
    email_repo = _FakeEmailRepository()
    crm_repo = _FakeCrmRepository()

    async def failing_fetch(config, folder, watermark):
        raise ImapAuthError("Login IMAP recusado pelo servidor (result='NO').")

    worker = EmailSyncWorker(
        account_repository=account_repo,
        integration_repository=integration_repo,
        email_repository=email_repo,
        crm_repository=crm_repo,
        fetch_messages=failing_fetch,
    )

    await worker.poll_once()

    assert account_repo.accounts[account.id].status == EmailAccountStatus.ERROR
    assert integration_repo.save_calls == 0
    assert email_repo.upsert_calls == []


@pytest.mark.asyncio
async def test_poll_once_associates_email_to_contact_by_from_address_case_insensitive() -> None:
    """email-client-imap-mvp-task-inbox-4-unit-1 (REQ-006): match
    case-insensitive entre `from_address` e `Contact.email` (mesmo user)."""
    integration = _integration()
    account = _account(is_active=True, integration_id=integration.id)
    contact = Contact(
        id=str(uuid.uuid4()),
        user_id=account.user_id,
        name="Jane Doe",
        email="jane@example.com",
    )

    account_repo = _FakeEmailAccountRepository([account])
    integration_repo = _FakeUserIntegrationRepository([integration])
    email_repo = _FakeEmailRepository()
    crm_repo = _FakeCrmRepository([contact])

    async def fake_fetch(config, folder, watermark):
        return [_message(from_address="Jane@Example.com")]

    worker = EmailSyncWorker(
        account_repository=account_repo,
        integration_repository=integration_repo,
        email_repository=email_repo,
        crm_repository=crm_repo,
        fetch_messages=fake_fetch,
    )

    await worker.poll_once()

    assert len(email_repo.upsert_calls) == 1
    _, _, contact_id = email_repo.upsert_calls[0]
    assert contact_id == contact.id
    assert crm_repo.get_by_email_calls == [
        (account.user_id, "Jane@Example.com")
    ]


@pytest.mark.asyncio
async def test_poll_once_passes_none_contact_id_when_no_match() -> None:
    """email-client-imap-mvp-task-inbox-4-unit-1 (REQ-006): sem match,
    `contact_id=None` e nenhum erro."""
    integration = _integration()
    account = _account(is_active=True, integration_id=integration.id)

    account_repo = _FakeEmailAccountRepository([account])
    integration_repo = _FakeUserIntegrationRepository([integration])
    email_repo = _FakeEmailRepository()
    crm_repo = _FakeCrmRepository()  # sem contatos cadastrados

    async def fake_fetch(config, folder, watermark):
        return [_message()]

    worker = EmailSyncWorker(
        account_repository=account_repo,
        integration_repository=integration_repo,
        email_repository=email_repo,
        crm_repository=crm_repo,
        fetch_messages=fake_fetch,
    )

    await worker.poll_once()

    assert len(email_repo.upsert_calls) == 1
    _, _, contact_id = email_repo.upsert_calls[0]
    assert contact_id is None
    assert account_repo.accounts[account.id].status == EmailAccountStatus.CONNECTED


@pytest.mark.asyncio
async def test_poll_once_marks_error_when_integration_type_is_not_imap() -> None:
    """Defesa contra `user_integrations` legada com `integration_type='smtp'`
    (stub vazio) e `config={}` apontada por `email_accounts`.

    Bug de produção (2026-08-10): o worker tentava `ImapIntegrationConfig(**{})`
    fora do `try/except` e o `pydantic.ValidationError` matava o `poll_once`
    inteiro. Agora: marca `status='error'` na conta, NÃO toca a credencial, e
    segue para a próxima conta.
    """
    now = datetime.now(UTC)
    legacy_integration = UserIntegration(
        id=str(uuid.uuid4()),
        user_id="user-a",
        integration_type="smtp",  # LEGADO: stub vazio, `config={}`
        config={},
        created_at=now,
        updated_at=now,
    )
    account = _account(is_active=True, integration_id=legacy_integration.id)

    account_repo = _FakeEmailAccountRepository([account])
    integration_repo = _FakeUserIntegrationRepository([legacy_integration])
    email_repo = _FakeEmailRepository()
    crm_repo = _FakeCrmRepository()

    fetch_calls: list[tuple[str, str]] = []

    async def fake_fetch(config, folder, watermark):
        fetch_calls.append((config.imap_username, folder))
        return []

    worker = EmailSyncWorker(
        account_repository=account_repo,
        integration_repository=integration_repo,
        email_repository=email_repo,
        crm_repository=crm_repo,
        fetch_messages=fake_fetch,
    )

    await worker.poll_once()  # NÃO deve levantar

    assert account_repo.accounts[account.id].status == EmailAccountStatus.ERROR
    assert integration_repo.save_calls == 0  # credencial intocada
    assert fetch_calls == []  # fetch_messages não foi chamado
    assert email_repo.upsert_calls == []


@pytest.mark.asyncio
async def test_poll_once_marks_error_when_config_fails_pydantic_validation() -> None:
    """Defesa contra `config` parcial/malformado: a integração é do tipo
    certo (`imap`) mas falta um campo obrigatório — não pode derrubar o loop.
    """
    now = datetime.now(UTC)
    broken_integration = UserIntegration(
        id=str(uuid.uuid4()),
        user_id="user-a",
        integration_type="imap",
        config={"imap_host": "imap.example.com"},  # faltam todos os outros
        created_at=now,
        updated_at=now,
    )
    account = _account(is_active=True, integration_id=broken_integration.id)

    account_repo = _FakeEmailAccountRepository([account])
    integration_repo = _FakeUserIntegrationRepository([broken_integration])
    email_repo = _FakeEmailRepository()
    crm_repo = _FakeCrmRepository()

    fetch_calls: list[tuple[str, str]] = []

    async def fake_fetch(config, folder, watermark):
        fetch_calls.append((config.imap_username, folder))
        return []

    worker = EmailSyncWorker(
        account_repository=account_repo,
        integration_repository=integration_repo,
        email_repository=email_repo,
        crm_repository=crm_repo,
        fetch_messages=fake_fetch,
    )

    await worker.poll_once()  # NÃO deve levantar

    assert account_repo.accounts[account.id].status == EmailAccountStatus.ERROR
    assert integration_repo.save_calls == 0  # credencial intocada
    assert fetch_calls == []
    assert email_repo.upsert_calls == []


@pytest.mark.asyncio
async def test_poll_once_continues_after_marking_error_on_one_account() -> None:
    """Uma conta ruim não pode impedir que outras contas sincronizem.

    Cobre a regressão do bug 2026-08-10: o `pydantic.ValidationError`
    saía do `_poll_account` e matava o `for account in accounts` no
    `poll_once`. Agora uma exceção aqui é contida em `_mark_error` /
    `try/except` interno e o loop segue para a próxima conta.
    """
    # Conta A: malformada (integration_type errado).
    now = datetime.now(UTC)
    bad_integration = UserIntegration(
        id=str(uuid.uuid4()),
        user_id="user-a",
        integration_type="smtp",
        config={},
        created_at=now,
        updated_at=now,
    )
    bad_account = _account(is_active=True, integration_id=bad_integration.id)

    # Conta B: saudável.
    good_integration = _integration()
    good_account = _account(is_active=True, integration_id=good_integration.id)

    account_repo = _FakeEmailAccountRepository([bad_account, good_account])
    integration_repo = _FakeUserIntegrationRepository(
        [bad_integration, good_integration]
    )
    email_repo = _FakeEmailRepository()
    crm_repo = _FakeCrmRepository()

    async def fake_fetch(config, folder, watermark):
        return [_message()]

    worker = EmailSyncWorker(
        account_repository=account_repo,
        integration_repository=integration_repo,
        email_repository=email_repo,
        crm_repository=crm_repo,
        fetch_messages=fake_fetch,
    )

    await worker.poll_once()  # NÃO deve levantar

    assert account_repo.accounts[bad_account.id].status == EmailAccountStatus.ERROR
    assert account_repo.accounts[good_account.id].status == EmailAccountStatus.CONNECTED
    assert len(email_repo.upsert_calls) == 1
    assert email_repo.upsert_calls[0][0] == good_account.id
