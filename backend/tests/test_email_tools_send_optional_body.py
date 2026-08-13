"""Teste do tool `send_email` para o contrato opcional de `body_text`
(email-send-html-only-by-default-task-tool-1, REQ-010).

Cobre: o tool aceita uma chamada com `body_text` omitido, e o `SendEmail`
subjacente é chamado com `body_text=None`.
"""
from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import pytest

import src.tools.email_tools as et
from src.application.ports.email_account_repository import (
    EmailAccountRepositoryPort,
)
from src.application.ports.email_repository import EmailRepositoryPort
from src.application.ports.user_integration_repository import (
    UserIntegrationRepositoryPort,
)
from src.domain.email import EmailAccount, EmailAccountStatus
from src.domain.integrations import UserIntegration


# ---- Fakes -----------------------------------------------------------------


class _FakeEmailAccountRepository(EmailAccountRepositoryPort):
    def __init__(self) -> None:
        self.accounts: dict[str, EmailAccount] = {}

    async def get(self, user_id: str, account_id: str) -> EmailAccount | None:
        account = self.accounts.get(account_id)
        if account is None or account.user_id != user_id:
            return None
        return account

    async def create(self, account: EmailAccount) -> EmailAccount:
        self.accounts[account.id] = account
        return account

    async def list_by_user(self, user_id: str) -> list[EmailAccount]:
        return [a for a in self.accounts.values() if a.user_id == user_id]

    async def list_all(self) -> list[EmailAccount]:
        return list(self.accounts.values())

    async def update(self, account: EmailAccount) -> EmailAccount | None:
        return account

    async def delete(self, user_id: str, account_id: str) -> bool:
        return False


class _FakeUserIntegrationRepository(UserIntegrationRepositoryPort):
    async def save(self, integration: UserIntegration) -> None:
        pass

    async def get(self, integration_id: str) -> UserIntegration | None:
        integration = UserIntegration(
            id=integration_id,
            user_id="user-a",
            integration_type="imap",
            config={
                "imap_host": "imap.example.com",
                "imap_port": 993,
                "imap_username": "user@example.com",
                "imap_password": "secret",
                "smtp_host": "smtp.example.com",
                "smtp_port": 587,
            },
        )
        return integration

    async def list_by_user(self, user_id: str) -> list[UserIntegration]:
        return []

    async def list_all(self) -> list[UserIntegration]:
        return []

    async def delete(self, integration_id: str) -> None:
        pass


class _FakeEmailRepository(EmailRepositoryPort):
    async def upsert_email(self, *args: Any, **kwargs: Any) -> Any:
        return None

    async def list_by_account(self, *args: Any, **kwargs: Any) -> list[Any]:
        return []

    async def get(self, *args: Any, **kwargs: Any) -> Any:
        return None

    async def get_by_message_id(self, *args: Any, **kwargs: Any) -> Any:
        return None

    async def mark_read(self, *args: Any, **kwargs: Any) -> bool:
        return True

    async def search(self, *args: Any, **kwargs: Any) -> list[Any]:
        return []

    async def move_folder(self, *args: Any, **kwargs: Any) -> bool:
        return False


# ---- Spy on SendEmail ------------------------------------------------------


@dataclass
class _Call:
    user_id: str
    account_id: str
    body_text: str | None
    body_html: str | None


class _SpySendEmail:
    instances: list["_SpySendEmail"] = []
    calls: list[_Call] = []

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        _SpySendEmail.instances.append(self)

    async def execute(
        self,
        *,
        user_id: str,
        account_id: str,
        to_addresses: list[str],
        subject: str,
        body_text: str | None = None,
        body_html: str | None = None,
        cc_addresses: list[str] | None = None,
        bcc_addresses: list[str] | None = None,
        in_reply_to: str | None = None,
        references: str | None = None,
        attachments: Any = None,
    ) -> Any:
        from src.application.use_cases.send_email import SendEmailResult

        _SpySendEmail.calls.append(
            _Call(
                user_id=user_id,
                account_id=account_id,
                body_text=body_text,
                body_html=body_html,
            )
        )
        return SendEmailResult(
            message_id=f"msg-{uuid.uuid4()}",
            sent_at=datetime.now(UTC),
            thread_id=None,
        )


# ---- Helpers ---------------------------------------------------------------


def _seed_account(accounts_repo: _FakeEmailAccountRepository, *, user_id: str) -> str:
    account_id = str(uuid.uuid4())
    account = EmailAccount(
        id=account_id,
        user_id=user_id,
        user_integration_id=str(uuid.uuid4()),
        display_name="Test",
        provider="imap",
        status=EmailAccountStatus.CONNECTED,
        is_active=True,
    )
    accounts_repo.accounts[account_id] = account
    return account_id


async def _stub_resolve_user_id(monkeypatch: pytest.MonkeyPatch, user_id: str) -> None:
    async def _fake() -> str | None:
        return user_id

    monkeypatch.setattr(et, "resolve_user_id", _fake)


# ---- Test ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_email_tool_forwards_body_text_none_when_omitted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """unit: o tool aceita uma chamada com `body_text` omitido e o use case
    é invocado com `body_text=None`."""
    _SpySendEmail.calls.clear()
    _SpySendEmail.instances.clear()

    user_id = "user-a"
    await _stub_resolve_user_id(monkeypatch, user_id)

    accounts_repo = _FakeEmailAccountRepository()
    account_id = _seed_account(accounts_repo, user_id=user_id)

    monkeypatch.setattr(et, "_email_repository", lambda: _FakeEmailRepository())
    monkeypatch.setattr(et, "_email_account_repository", lambda: accounts_repo)
    monkeypatch.setattr(et, "_integration_repository", lambda: _FakeUserIntegrationRepository())
    monkeypatch.setattr(et, "SendEmail", _SpySendEmail)

    result = await et.send_email.ainvoke(
        {
            "account_id": account_id,
            "to_addresses": ["alice@example.com"],
            "subject": "Hello",
            "body_html": "<p>Hi</p>",
        }
    )

    assert isinstance(result, dict)
    assert "message_id" in result
    assert result["message_id"]

    assert len(_SpySendEmail.calls) == 1
    call = _SpySendEmail.calls[0]
    assert call.user_id == user_id
    assert call.account_id == account_id
    assert call.body_text is None
    assert call.body_html is not None
    assert "<p>Hi</p>" in call.body_html
