"""Testes do use case `SendEmail` para o contrato opcional de `body_text`
(email-send-html-only-by-default-task-usecase-1, REQ-010/REQ-011).

Cobre:
- HTML-only send chega em `send_email_via_smtp` com `body_text=None` e
  persiste o `ParsedMessage` com `body_text=None`.
- Plain-only send gera o HTML via `resolve_bodies` e persiste tanto o
  `body_text` original quanto o HTML gerado.
- Ambos vazios levanta `ValueError("Send body required")` antes de chamar
  o SMTP e antes de upsertar a Sent row.
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


# ---- Fakes (mirror of test_send_email_use_case.py, scoped) ---------------


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
    def __init__(self) -> None:
        self._by_user: dict[str, dict[str, Email]] = {}
        self.upserted: list[tuple[str, Any]] = []

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

    async def list_by_account(self, *args: Any, **kwargs: Any) -> list[Email]:
        return []

    async def get(self, *args: Any, **kwargs: Any) -> Email | None:
        return None

    async def get_by_message_id(self, *args: Any, **kwargs: Any) -> Email | None:
        return None

    async def search(self, *args: Any, **kwargs: Any) -> list[Email]:
        return []

    async def mark_read(self, *args: Any, **kwargs: Any) -> bool:
        return True

    async def move_folder(self, *args: Any, **kwargs: Any) -> bool:
        return False


class _SmtpCallRecorder:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def __call__(self, **kwargs: Any) -> str:
        self.calls.append(kwargs)
        return f"<{uuid.uuid4()}@sent.example.com>"


# ---- Fixtures -------------------------------------------------------------


_VALID_CONFIG = {
    "imap_host": "imap.example.com",
    "imap_port": 993,
    "imap_username": "user@example.com",
    "imap_password": "secret",
    "smtp_host": "smtp.example.com",
    "smtp_port": 587,
}


def _build_imap_account(
    *, user_id: str, account_id: str
) -> tuple[EmailAccount, UserIntegration]:
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


# ---- Tests ----------------------------------------------------------------


async def test_send_email_html_only_forwards_none_to_smtp_and_persists_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """unit: body_text=None + body_html="<p>Hi</p>" → SMTP recebe (None, html)
    e o `ParsedMessage` upserted tem `body_text=None`."""
    from src.application.use_cases import send_email as send_email_module
    from src.application.use_cases.send_email import SendEmail

    user_id = "user-a"
    account_id = "acc-a1"
    account, integration = _build_imap_account(user_id=user_id, account_id=account_id)

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
        subject="Hello",
        body_text=None,
        body_html="<p>Hi</p>",
    )

    # SMTP recebeu a chamada com o par (None, html)
    assert len(recorder.calls) == 1
    call = recorder.calls[0]
    assert call["body_text"] is None
    assert call["body_html"] is not None
    assert "Hi" in call["body_html"]

    # O Sent row foi upserted com body_text=None
    assert len(email_repo.upserted) == 1
    saved_account_id, saved_message = email_repo.upserted[0]
    assert saved_account_id == account_id
    assert saved_message.body_text is None
    assert saved_message.body_html is not None
    assert "Hi" in saved_message.body_html
    assert result.message_id


async def test_send_email_raises_when_both_bodies_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """unit: body_text=None + body_html=None → ValueError("Send body required"),
    SMTP NÃO é chamado e o Sent row NÃO é upserted."""
    from src.application.use_cases import send_email as send_email_module
    from src.application.use_cases.send_email import SendEmail

    user_id = "user-a"
    account_id = "acc-a1"
    account, integration = _build_imap_account(user_id=user_id, account_id=account_id)

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
    with pytest.raises(ValueError, match="Send body required"):
        await use_case.execute(
            user_id=user_id,
            account_id=account_id,
            to_addresses=["alice@example.com"],
            subject="Hello",
            body_text=None,
            body_html=None,
        )

    assert recorder.calls == []
    assert email_repo.upserted == []


async def test_send_email_plain_only_persists_generated_html(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """unit: body_text="Hi" + body_html=None → SMTP recebe o par resolvido
    (text="Hi", html="<p>Hi</p>") e o Sent row guarda ambos."""
    from src.application.use_cases import send_email as send_email_module
    from src.application.use_cases.send_email import SendEmail

    user_id = "user-a"
    account_id = "acc-a1"
    account, integration = _build_imap_account(user_id=user_id, account_id=account_id)

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
    await use_case.execute(
        user_id=user_id,
        account_id=account_id,
        to_addresses=["alice@example.com"],
        subject="Hello",
        body_text="Hi",
        body_html=None,
    )

    assert len(recorder.calls) == 1
    call = recorder.calls[0]
    assert call["body_text"] == "Hi"
    assert call["body_html"] is not None
    assert "<p>" in call["body_html"]
    assert "Hi" in call["body_html"]

    assert len(email_repo.upserted) == 1
    saved_account_id, saved_message = email_repo.upserted[0]
    assert saved_account_id == account_id
    assert saved_message.body_text == "Hi"
    assert saved_message.body_html is not None
    assert "<p>" in saved_message.body_html
