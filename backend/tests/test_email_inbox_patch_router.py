"""Testes de `PATCH /api/email/{id}` (task `email-client-imap-mvp-task-inbox-3`).

Cobre o unit-test linkado à task no OpenSddRag:

- unit-1 (REQ-004): PATCH `{"is_read": true}` em email não-lido do próprio
  user resulta em `is_read=true` no GET subsequente; PATCH `{"folder":
  "Archive"}` move o email — listagem filtrada por "Archive" inclui e
  filtrada por "INBOX" não inclui mais.

Padrão consistente com `test_email_inbox_router.py`: repositório fake
injetado via override de dependency, sem Postgres real.
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
        row = self._get(user_id, email_id)
        if row is None:
            return False
        row.folder = folder
        return True


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
        body_html=None,
        received_at=datetime(2026, 1, 1, tzinfo=UTC),
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
# unit-1 (REQ-004): PATCH alterna is_read e move folder; ambos escopados ao user
# ===========================================================================


def test_patch_marks_owned_email_as_read(
    client: TestClient, emails_repo: _FakeEmailRepository
) -> None:
    """PATCH {"is_read": true} flips o flag; GET subsequente reflete."""
    _as(_USER_A)
    account = "acc-a1"
    row = _seed_row(
        _USER_A.id,
        account_id=account,
        folder="INBOX",
        subject="Unread message",
        body_text="",
        from_address="sender@example.com",
    )
    emails_repo._add(_USER_A.id, row)
    assert row.is_read is False

    resp = client.patch(f"/api/email/{row.id}", json={"is_read": True})

    assert resp.status_code == 200, resp.text
    assert resp.json()["is_read"] is True

    follow = client.get(f"/api/email/{row.id}")
    assert follow.status_code == 200
    assert follow.json()["is_read"] is True


def test_patch_moves_owned_email_to_another_folder(
    client: TestClient, emails_repo: _FakeEmailRepository
) -> None:
    """PATCH {"folder": "Archive"} move o email; listagem reflete."""
    _as(_USER_A)
    account = "acc-a1"
    row = _seed_row(
        _USER_A.id,
        account_id=account,
        folder="INBOX",
        subject="To be archived",
        body_text="",
        from_address="sender@example.com",
    )
    emails_repo._add(_USER_A.id, row)

    resp = client.patch(f"/api/email/{row.id}", json={"folder": "Archive"})

    assert resp.status_code == 200, resp.text
    assert resp.json()["folder"] == "Archive"

    listed_archive = client.get("/api/email?folder=Archive")
    assert listed_archive.status_code == 200
    assert any(item["id"] == row.id for item in listed_archive.json())

    listed_inbox = client.get("/api/email?folder=INBOX")
    assert listed_inbox.status_code == 200
    assert all(item["id"] != row.id for item in listed_inbox.json())
