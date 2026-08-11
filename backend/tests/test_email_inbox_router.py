"""Testes de `GET /api/email` e `GET /api/email/{id}` (task `email-client-imap-mvp-task-inbox-2`).

Cobre o unit-test linkado à task no OpenSddRag:

- unit-1 (REQ-001/REQ-002): GIVEN user A autenticado com emails em duas contas,
  WHEN `GET /api/email?account_id=X&folder=INBOX`, THEN só as linhas de X/INBOX.
  WHEN `GET /api/email/{id}` para um email do user B, THEN status 404.

Padrão consistente com `test_email_router.py`: repositório fake injetado via
override de dependency, sem Postgres real, sem rede.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

import src.infrastructure.web.email_router as email_router
import src.infrastructure.web.webapp as webapp
from src.application.ports.email_repository import EmailRepositoryPort
from src.domain.email import Email
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
_USER_B = User(
    id="user-b",
    username="bob",
    password_hash="h",
    role="user",
    is_active=True,
    created_at=datetime(2026, 1, 1, tzinfo=UTC),
)


@dataclass
class _StoredEmail:
    """Estado cru de um email no fake — espelha o que o repositório guardaria."""

    id: str
    email_account_id: str
    message_id: str
    folder: str
    from_address: str
    to_addresses: list[str]
    subject: str | None
    body_text: str | None
    body_html: str | None
    is_read: bool = False
    received_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class _FakeEmailRepository(EmailRepositoryPort):
    """In-memory implementation do `EmailRepositoryPort` para os testes de router."""

    def __init__(self) -> None:
        self._by_user: dict[str, dict[str, _StoredEmail]] = {}

    def _add(self, user_id: str, row: _StoredEmail) -> None:
        self._by_user.setdefault(user_id, {})[row.id] = row

    def _get(self, user_id: str, email_id: str) -> _StoredEmail | None:
        return self._by_user.get(user_id, {}).get(email_id)

    async def upsert_email(
        self,
        email_account_id: str,
        message: Any,
        attachments: Any = None,
    ) -> Email:
        raise NotImplementedError

    async def list_by_account(
        self,
        user_id: str,
        account_id: str | None,
        folder: str | None,
        limit: int,
        offset: int,
    ) -> list[Email]:
        rows = list(self._by_user.get(user_id, {}).values())
        if account_id is not None:
            rows = [r for r in rows if r.email_account_id == account_id]
        if folder is not None:
            rows = [r for r in rows if r.folder == folder]
        rows.sort(key=lambda r: r.received_at, reverse=True)
        return [_to_email(r) for r in rows[offset : offset + limit]]

    async def get(self, user_id: str, email_id: str) -> Email | None:
        row = self._get(user_id, email_id)
        if row is None:
            return None
        return _to_email(row)

    async def get_by_message_id(
        self, user_id: str, message_id: str
    ) -> Email | None:
        return None

    async def mark_read(self, user_id: str, email_id: str) -> bool:
        row = self._get(user_id, email_id)
        if row is None:
            return False
        row.is_read = True
        return True

    async def search(
        self,
        user_id: str,
        account_id: str | None,
        query: str,
        limit: int,
    ) -> list[Email]:
        raise NotImplementedError

    async def move_folder(self, user_id: str, email_id: str, folder: str) -> bool:
        raise NotImplementedError


def _to_email(row: _StoredEmail) -> Email:
    return Email(
        id=row.id,
        email_account_id=row.email_account_id,
        message_id=row.message_id,
        thread_id=None,
        folder=row.folder,
        from_address=row.from_address,
        from_name=None,
        to_addresses=list(row.to_addresses),
        cc_addresses=[],
        bcc_addresses=[],
        subject=row.subject,
        body_html=row.body_html,
        body_text=row.body_text,
        is_read=row.is_read,
        is_starred=False,
        has_attachments=False,
        contact_id=None,
        received_at=row.received_at,
        created_at=row.received_at,
    )


def _seed_row(
    user_id: str,
    *,
    account_id: str,
    folder: str,
    subject: str,
    body_text: str,
    from_address: str,
    received_at: datetime,
    body_html: str | None = None,
) -> _StoredEmail:
    return _StoredEmail(
        id=str(uuid.uuid4()),
        email_account_id=account_id,
        message_id=f"msg-{uuid.uuid4()}",
        folder=folder,
        from_address=from_address,
        to_addresses=["user@example.com"],
        subject=subject,
        body_text=body_text,
        body_html=body_html,
        received_at=received_at,
    )


@pytest.fixture
def emails_repo() -> _FakeEmailRepository:
    return _FakeEmailRepository()


@pytest.fixture
def client(emails_repo: _FakeEmailRepository):
    webapp.app.dependency_overrides[email_router._email_repository] = (
        lambda: emails_repo
    )
    try:
        yield TestClient(webapp.app)
    finally:
        webapp.app.dependency_overrides.pop(require_auth, None)
        webapp.app.dependency_overrides.pop(email_router._email_repository, None)


def _as(user: User) -> None:
    webapp.app.dependency_overrides[require_auth] = lambda: user


# ===========================================================================
# unit-1 (REQ-001/REQ-002): listagem filtrada por account_id+folder, e
# get-by-id de email de outro user retorna 404
# ===========================================================================


def test_list_emails_filters_by_account_id_and_folder(
    client: TestClient, emails_repo: _FakeEmailRepository
) -> None:
    """GET /api/email?account_id=X&folder=Inbox retorna só linhas que casam com X/INBOX."""
    _as(_USER_A)
    account_a1 = "acc-a1"
    account_a2 = "acc-a2"
    base = datetime(2026, 1, 1, tzinfo=UTC)

    # Email do user A na account A1, pasta INBOX — deve aparecer.
    emails_repo._add(
        _USER_A.id,
        _seed_row(
            _USER_A.id,
            account_id=account_a1,
            folder="INBOX",
            subject="A1 Inbox match",
            body_text="hi",
            from_address="alice@example.com",
            received_at=base,
        ),
    )
    # Email do user A na account A1, pasta Sent — NÃO deve aparecer.
    emails_repo._add(
        _USER_A.id,
        _seed_row(
            _USER_A.id,
            account_id=account_a1,
            folder="Sent",
            subject="A1 Sent",
            body_text="",
            from_address="bob@example.com",
            received_at=base + timedelta(hours=1),
        ),
    )
    # Email do user A na account A2, pasta INBOX — NÃO deve aparecer (conta errada).
    emails_repo._add(
        _USER_A.id,
        _seed_row(
            _USER_A.id,
            account_id=account_a2,
            folder="INBOX",
            subject="A2 Inbox (wrong account)",
            body_text="",
            from_address="carol@example.com",
            received_at=base + timedelta(hours=2),
        ),
    )

    resp = client.get(f"/api/email?account_id={account_a1}&folder=INBOX")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body) == 1
    assert body[0]["subject"] == "A1 Inbox match"
    assert body[0]["email_account_id"] == account_a1
    assert body[0]["folder"] == "INBOX"


def test_get_email_for_other_users_email_returns_404(
    client: TestClient, emails_repo: _FakeEmailRepository
) -> None:
    """GET /api/email/{id} para um email de outro user retorna 404 (não 200 nem 403)."""
    _as(_USER_A)
    account = "acc-a1"
    private_row = _seed_row(
        _USER_A.id,
        account_id=account,
        folder="INBOX",
        subject="Private",
        body_text="secret",
        from_address="sender@example.com",
        received_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    emails_repo._add(_USER_A.id, private_row)

    _as(_USER_B)
    resp = client.get(f"/api/email/{private_row.id}")

    assert resp.status_code == 404
    assert "secret" not in resp.text
