"""Testes do `POST /api/email/send` para o contrato opcional de `body_text`
(email-send-html-only-by-default-task-route-1, REQ-010).

Cobre:
- body_html-only (sem body_text) → 201, use case chamado com body_text=None.
- ambos vazios (body_text=null + body_html=null, ou ambos omitidos) → 422,
  use case nunca chamado.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

import src.infrastructure.web.email_router as email_router
import src.infrastructure.web.webapp as webapp
from src.application.ports.email_account_repository import (
    EmailAccountRepositoryPort,
)
from src.application.ports.email_repository import EmailRepositoryPort
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
    created_at=datetime(2026, 1, 1, tzinfo=UTC),
)


# ---- Fakes (compact mirrors of test_email_send_router.py) -----------------


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
    def __init__(self) -> None:
        self.integrations: dict[str, UserIntegration] = {}

    async def save(self, integration: UserIntegration) -> None:
        self.integrations[integration.id] = integration

    async def get(self, integration_id: str) -> UserIntegration | None:
        return self.integrations.get(integration_id)

    async def list_by_user(self, user_id: str) -> list[UserIntegration]:
        return list(self.integrations.values())

    async def list_all(self) -> list[UserIntegration]:
        return list(self.integrations.values())

    async def delete(self, integration_id: str) -> None:
        pass


@dataclass
class _FakeCallRecord:
    user_id: str
    account_id: str
    to_addresses: list[str]
    subject: str
    body_text: str | None
    body_html: str | None


class _FakeSendEmail:
    instances: list["_FakeSendEmail"] = []

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.calls: list[_FakeCallRecord] = []
        _FakeSendEmail.instances.append(self)

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

        account_repo: _FakeEmailAccountRepository = self.kwargs["email_account_repository"]
        account = await account_repo.get(user_id, account_id)
        if account is None:
            raise ValueError("Email account not found")

        self.calls.append(
            _FakeCallRecord(
                user_id=user_id,
                account_id=account_id,
                to_addresses=list(to_addresses),
                subject=subject,
                body_text=body_text,
                body_html=body_html,
            )
        )
        return SendEmailResult(
            message_id=f"msg-{uuid.uuid4()}",
            sent_at=datetime.now(UTC),
            thread_id=None,
        )


class _FakeEmailRepository(EmailRepositoryPort):
    async def upsert_email(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError

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


# ---- Fixtures --------------------------------------------------------------


@pytest.fixture
def accounts_repo() -> _FakeEmailAccountRepository:
    return _FakeEmailAccountRepository()


@pytest.fixture
def integrations_repo() -> _FakeUserIntegrationRepository:
    return _FakeUserIntegrationRepository()


@pytest.fixture
def emails_repo() -> _FakeEmailRepository:
    return _FakeEmailRepository()


@pytest.fixture
def client(
    accounts_repo: _FakeEmailAccountRepository,
    integrations_repo: _FakeUserIntegrationRepository,
    emails_repo: _FakeEmailRepository,
    monkeypatch: pytest.MonkeyPatch,
):
    _FakeSendEmail.instances.clear()
    monkeypatch.setattr(email_router, "SendEmail", _FakeSendEmail)

    webapp.app.dependency_overrides[email_router._email_account_repository] = (
        lambda: accounts_repo
    )
    webapp.app.dependency_overrides[email_router._user_integration_repository] = (
        lambda: integrations_repo
    )
    webapp.app.dependency_overrides[email_router._email_repository] = lambda: emails_repo
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
        webapp.app.dependency_overrides.pop(email_router._email_repository, None)


def _as(user: User) -> None:
    webapp.app.dependency_overrides[require_auth] = lambda: user


def _seed_account(accounts_repo: _FakeEmailAccountRepository, *, user_id: str) -> str:
    account_id = str(uuid.uuid4())
    integration_id = str(uuid.uuid4())
    account = EmailAccount(
        id=account_id,
        user_id=user_id,
        user_integration_id=integration_id,
        display_name="Test",
        provider="imap",
    )
    accounts_repo.accounts[account_id] = account
    return account_id


# ---- Tests -----------------------------------------------------------------


def test_send_email_accepts_body_html_only(
    client: TestClient,
    accounts_repo: _FakeEmailAccountRepository,
) -> None:
    """unit: body sem `body_text` mas com `body_html` → 201, use case chamado
    com `body_text=None`."""
    _as(_USER_A)
    account_id = _seed_account(accounts_repo, user_id=_USER_A.id)

    body = {
        "account_id": account_id,
        "to_addresses": ["alice@example.com"],
        "subject": "Hello",
        "body_html": "<p>Hi</p>",
    }

    resp = client.post("/api/email/send", json=body)

    assert resp.status_code == 201, resp.text
    resp_body = resp.json()
    assert resp_body["message_id"]

    assert len(_FakeSendEmail.instances) == 1
    fake = _FakeSendEmail.instances[0]
    assert len(fake.calls) == 1
    call = fake.calls[0]
    assert call.body_text is None
    assert call.body_html is not None
    assert "<p>Hi</p>" in call.body_html


def test_send_email_rejects_when_both_bodies_empty(
    client: TestClient,
    accounts_repo: _FakeEmailAccountRepository,
) -> None:
    """unit: body_text=null + body_html=null → 422, use case nunca chamado."""
    _as(_USER_A)
    account_id = _seed_account(accounts_repo, user_id=_USER_A.id)

    body = {
        "account_id": account_id,
        "to_addresses": ["alice@example.com"],
        "subject": "Hello",
        "body_text": None,
        "body_html": None,
    }

    resp = client.post("/api/email/send", json=body)

    assert resp.status_code == 422, resp.text
    # Use case nunca é instanciado
    assert _FakeSendEmail.instances == []
