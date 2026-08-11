"""Testes do use case `SendEmail` (email-client-imap-mvp-task-send-1).

Cobre o unit-test linkado à task no OpenSddRag:

- unit-1 (REQ-005): `SendEmail.execute` despacha via SMTP com
  to/cc/bcc/subject/body do request; reply preserva `thread_id` e prefixa
  `Re:` no subject (sem duplo-prefixo); conta de outro user é rejeitada
  sem chamar SMTP.

Mesmo padrão de `test_email_account_use_cases.py` — repositórios são
fakes injetados no use case, sem Postgres real; o `send_email_via_smtp`
de `smtp_client` é monkey-patched para evitar I/O de rede e para
permitir inspeção dos argumentos.
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
from src.domain.email import Email, EmailAccount, EmailAccountStatus
from src.domain.integrations import UserIntegration

# ===========================================================================
# Fakes
# ===========================================================================


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


class _FakeEmailRepository(EmailRepositoryPort):
    """In-memory fake; `get`, `upsert_email` e `mark_read` são exercitados pelo `SendEmail`."""

    def __init__(self) -> None:
        self._by_user: dict[str, dict[str, Email]] = {}
        self.upserted: list[tuple[str, Any]] = []
        self.marked_read: list[tuple[str, str]] = []

    def add(self, user_id: str, email: Email) -> None:
        self._by_user.setdefault(user_id, {})[email.id] = email

    async def upsert_email(
        self,
        email_account_id: str,
        message: Any,
        attachments: Any = None,
        contact_id: str | None = None,
    ) -> Email:
        self.upserted.append((email_account_id, message))
        return Email(
            id=str(uuid.uuid4()),
            email_account_id=email_account_id,
            message_id=message.message_id,
            thread_id=None,
            folder=message.folder,
            from_address=message.from_address,
            from_name=message.from_name,
            to_addresses=list(message.to_addresses),
            cc_addresses=[],
            bcc_addresses=[],
            subject=message.subject,
            body_html=message.body_html,
            body_text=message.body_text,
            is_read=False,
            is_starred=False,
            has_attachments=bool(attachments),
            contact_id=contact_id,
            received_at=message.received_at,
        )

    async def list_by_account(
        self,
        user_id: str,
        account_id: str | None = None,
        folder: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[Email]:
        return []

    async def get(self, user_id: str, email_id: str) -> Email | None:
        return self._by_user.get(user_id, {}).get(email_id)

    async def get_by_message_id(
        self, user_id: str, message_id: str
    ) -> Email | None:
        for email in self._by_user.get(user_id, {}).values():
            if email.message_id == message_id:
                return email
        return None

    async def search(
        self,
        user_id: str,
        account_id: str | None,
        query: str,
        limit: int,
    ) -> list[Email]:
        return []

    async def mark_read(self, user_id: str, email_id: str) -> bool:
        self.marked_read.append((user_id, email_id))
        return True

    async def move_folder(self, user_id: str, email_id: str, folder: str) -> bool:
        return False


# ===========================================================================
# Helpers
# ===========================================================================


_VALID_CONFIG = {
    "imap_host": "imap.example.com",
    "imap_port": 993,
    "imap_username": "user@example.com",
    "imap_password": "secret",
    "smtp_host": "smtp.example.com",
    "smtp_port": 587,
}


def _build_account(*, user_id: str, account_id: str) -> tuple[EmailAccount, UserIntegration]:
    integration = UserIntegration(
        id=str(uuid.uuid4()),
        user_id=user_id,
        integration_type="imap",
        config=dict(_VALID_CONFIG),
    )
    account = EmailAccount(
        id=account_id,
        user_id=user_id,
        user_integration_id=integration.id,
        display_name="Trabalho",
        status=EmailAccountStatus.CONNECTED,
    )
    return account, integration


def _build_email(
    *,
    user_id: str,
    account_id: str,
    thread_id: str | None,
    subject: str,
    message_id: str | None = None,
) -> Email:
    return Email(
        id=str(uuid.uuid4()),
        email_account_id=account_id,
        message_id=message_id or f"<{uuid.uuid4()}@example.com>",
        thread_id=thread_id,
        folder="INBOX",
        from_address="sender@example.com",
        from_name=None,
        to_addresses=["user@example.com"],
        cc_addresses=[],
        bcc_addresses=[],
        subject=subject,
        body_html=None,
        body_text="body",
        is_read=True,
        is_starred=False,
        has_attachments=False,
        contact_id=None,
        received_at=datetime(2026, 1, 1, tzinfo=UTC),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


class _SmtpCallRecorder:
    """Captura todas as chamadas ao `send_email_via_smtp` para inspeção."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def __call__(self, **kwargs: Any) -> str:
        self.calls.append(kwargs)
        return f"<{uuid.uuid4()}@sent.example.com>"


# ===========================================================================
# Testes
# ===========================================================================


async def test_send_email_dispatches_with_matching_recipients_subject_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REQ-005: novos envios via SMTP de conta owned despacham com to/cc/bcc/subject/body do request."""
    from src.application.use_cases import send_email as send_email_module
    from src.application.use_cases.send_email import SendEmail

    user_id = "user-a"
    account_id = "acc-a1"
    account, integration = _build_account(user_id=user_id, account_id=account_id)

    accounts_repo = _FakeEmailAccountRepository()
    accounts_repo.accounts[account.id] = account
    integrations_repo = _FakeUserIntegrationRepository()
    integrations_repo.integrations[integration.id] = integration
    email_repo = _FakeEmailRepository()

    recorder = _SmtpCallRecorder()
    monkeypatch.setattr(send_email_module, "send_email_via_smtp", recorder)

    use_case = SendEmail(
        email_account_repository=accounts_repo,
        integration_repository=integrations_repo,
        email_repository=email_repo,
    )
    result = await use_case.execute(
        user_id=user_id,
        account_id=account_id,
        to_addresses=["alice@example.com"],
        subject="Hello world",
        body_text="Hi there",
        cc_addresses=["bob@example.com"],
        bcc_addresses=["carol@example.com"],
    )

    assert len(recorder.calls) == 1
    call = recorder.calls[0]
    assert call["to_addresses"] == ["alice@example.com"]
    assert call["cc_addresses"] == ["bob@example.com"]
    assert call["bcc_addresses"] == ["carol@example.com"]
    assert call["subject"] == "Hello world"
    assert call["body_text"] == "Hi there"
    assert result.message_id  # Message-ID returned
    # New (non-reply) sends have no thread and no in_reply_to header.
    assert result.thread_id is None
    assert call["in_reply_to"] is None

    # The dispatched message is persisted into the account's Sent folder
    # (REQ-001 email-inbox — otherwise it can never appear in a
    # folder="Sent" listing) and marked read.
    assert len(email_repo.upserted) == 1
    saved_account_id, saved_message = email_repo.upserted[0]
    assert saved_account_id == account_id
    assert saved_message.folder == "Sent"
    assert saved_message.to_addresses == ["alice@example.com"]
    assert saved_message.subject == "Hello world"
    assert saved_message.message_id == result.message_id
    assert len(email_repo.marked_read) == 1
    assert email_repo.marked_read[0][0] == user_id


async def test_send_email_reply_propagates_thread_id_and_prefixes_subject(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REQ-005: reply preserva `thread_id` e adiciona `Re:` ao subject (sem duplo-prefixo)."""
    from src.application.use_cases import send_email as send_email_module
    from src.application.use_cases.send_email import SendEmail

    user_id = "user-a"
    account_id = "acc-a1"
    account, integration = _build_account(user_id=user_id, account_id=account_id)

    accounts_repo = _FakeEmailAccountRepository()
    accounts_repo.accounts[account.id] = account
    integrations_repo = _FakeUserIntegrationRepository()
    integrations_repo.integrations[integration.id] = integration
    email_repo = _FakeEmailRepository()

    # Original email (sem prefixo Re:) — deve virar "Re: Hello".
    original = _build_email(
        user_id=user_id,
        account_id=account_id,
        thread_id="T1",
        subject="Hello",
    )
    email_repo.add(user_id, original)

    recorder = _SmtpCallRecorder()
    monkeypatch.setattr(send_email_module, "send_email_via_smtp", recorder)

    use_case = SendEmail(
        email_account_repository=accounts_repo,
        integration_repository=integrations_repo,
        email_repository=email_repo,
    )
    result = await use_case.execute(
        user_id=user_id,
        account_id=account_id,
        to_addresses=["sender@example.com"],
        subject="Hello",
        body_text="Replying",
        in_reply_to=original.message_id,
    )

    assert result.thread_id == "T1"
    assert len(recorder.calls) == 1
    call = recorder.calls[0]
    assert call["subject"] == "Re: Hello"
    assert call["in_reply_to"] == original.message_id

    assert len(email_repo.upserted) == 1
    _, saved_message = email_repo.upserted[0]
    assert saved_message.folder == "Sent"
    assert saved_message.subject == "Re: Hello"


async def test_send_email_reply_does_not_double_prefix_subject(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REQ-005: reply a email já com prefixo `Re:` NÃO vira `Re: Re:`."""
    from src.application.use_cases import send_email as send_email_module
    from src.application.use_cases.send_email import SendEmail

    user_id = "user-a"
    account_id = "acc-a1"
    account, integration = _build_account(user_id=user_id, account_id=account_id)

    accounts_repo = _FakeEmailAccountRepository()
    accounts_repo.accounts[account.id] = account
    integrations_repo = _FakeUserIntegrationRepository()
    integrations_repo.integrations[integration.id] = integration
    email_repo = _FakeEmailRepository()

    original = _build_email(
        user_id=user_id,
        account_id=account_id,
        thread_id="T1",
        subject="Re: Hello",
    )
    email_repo.add(user_id, original)

    recorder = _SmtpCallRecorder()
    monkeypatch.setattr(send_email_module, "send_email_via_smtp", recorder)

    use_case = SendEmail(
        email_account_repository=accounts_repo,
        integration_repository=integrations_repo,
        email_repository=email_repo,
    )
    await use_case.execute(
        user_id=user_id,
        account_id=account_id,
        to_addresses=["sender@example.com"],
        subject="Re: Hello",
        body_text="Replying",
        in_reply_to=original.message_id,
    )

    call = recorder.calls[0]
    assert call["subject"] == "Re: Hello"


async def test_send_email_rejects_account_owned_by_different_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REQ-005: conta de outro user é rejeitada e SMTP não é chamado."""
    from src.application.use_cases import send_email as send_email_module
    from src.application.use_cases.send_email import SendEmail

    user_a = "user-a"
    user_b = "user-b"
    account_id = "acc-b1"
    # A conta pertence ao user-b; user-a tenta enviar.
    account, integration = _build_account(user_id=user_b, account_id=account_id)

    accounts_repo = _FakeEmailAccountRepository()
    accounts_repo.accounts[account.id] = account
    integrations_repo = _FakeUserIntegrationRepository()
    integrations_repo.integrations[integration.id] = integration
    email_repo = _FakeEmailRepository()

    recorder = _SmtpCallRecorder()
    monkeypatch.setattr(send_email_module, "send_email_via_smtp", recorder)

    use_case = SendEmail(
        email_account_repository=accounts_repo,
        integration_repository=integrations_repo,
        email_repository=email_repo,
    )
    with pytest.raises(ValueError):
        await use_case.execute(
            user_id=user_a,
            account_id=account_id,
            to_addresses=["alice@example.com"],
            subject="Hi",
            body_text="body",
        )

    # SMTP NÃO foi chamado, e nada foi persistido.
    assert recorder.calls == []
    assert email_repo.upserted == []


async def test_send_email_reply_resolves_target_by_message_id_not_db_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cobre a regressão 2026-08-10: o frontend envia o `Message-ID:` IMAP
    (string tipo `CAE3...@mail.gmail.com`) como `in_reply_to` no payload
    do `POST /api/email/send` — o `SendEmail.execute` precisa resolver
    pelo `message_id` da linha, NÃO pelo UUID do `id`. A versão anterior
    usava `email_repository.get(user_id, in_reply_to)` que tentava casar a
    string IMAP contra a coluna UUID e levantava
    `psycopg.errors.InvalidTextRepresentation`.
    """
    from src.application.use_cases import send_email as send_email_module
    from src.application.use_cases.send_email import SendEmail

    user_id = "user-a"
    account_id = "acc-a1"
    account, integration = _build_account(user_id=user_id, account_id=account_id)
    accounts_repo = _FakeEmailAccountRepository()
    accounts_repo.accounts[account.id] = account
    integrations_repo = _FakeUserIntegrationRepository()
    integrations_repo.integrations[integration.id] = integration
    email_repo = _FakeEmailRepository()

    # Original com `message_id` IMAP real (não é UUID).
    original_message_id = "CAE3MHj30HSdfmgQ9XTPmbFvbUK+JCO+uf6efOqaGO+QP7uR9CQ@mail.gmail.com"
    original = _build_email(
        user_id=user_id,
        account_id=account_id,
        thread_id="T-thread-1",
        subject="Original",
        message_id=original_message_id,
    )
    email_repo.add(user_id, original)

    recorder = _SmtpCallRecorder()
    monkeypatch.setattr(send_email_module, "send_email_via_smtp", recorder)

    use_case = SendEmail(
        email_account_repository=accounts_repo,
        integration_repository=integrations_repo,
        email_repository=email_repo,
    )

    # `in_reply_to` é o Message-ID IMAP, NÃO o UUID do `id`.
    result = await use_case.execute(
        user_id=user_id,
        account_id=account_id,
        to_addresses=["sender@example.com"],
        subject="Reply",
        body_text="Replying",
        in_reply_to=original_message_id,
    )

    assert result.thread_id == "T-thread-1"
    assert len(recorder.calls) == 1
    call = recorder.calls[0]
    # O subject prefixa `Re:` apenas uma vez.
    assert call["subject"] == "Re: Reply"
    # O SMTP `In-Reply-To:` carrega o Message-ID IMAP original.
    assert call["in_reply_to"] == original_message_id
