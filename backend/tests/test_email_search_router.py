"""Testes de `GET /api/email/search` (REQ-003 email-inbox).

Mesmo padrão de `test_email_inbox_router.py`: `EmailRepositoryPort` fake
injetado via `dependency_overrides`; `require_auth` é sobrescrito direto
no `webapp.app.dependency_overrides`. Sem Postgres real, sem rede.

Cobre os 2 cenários do spec REQ-003:

- Cenário 1: termo que aparece em subjects de emails de duas contas do
  mesmo user → ambos retornados (search atravessa contas próprias).
- Cenário 2: termo que só existe em emails de outro user → resultado
  vazio, sem vazar nada (cross-user nunca retorna).
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
    id: str
    email_account_id: str
    message_id: str
    folder: str
    from_address: str
    to_addresses: list[str]
    subject: str | None
    body_text: str | None
    received_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class _FakeEmailRepository(EmailRepositoryPort):
    """In-memory que implementa o scoping por `user_id` exatamente como a
    versão Postgres: cada `account_id` mapeia para um único `user_id`, e
    `search` filtra por esse mapeamento antes de casar o termo."""

    def __init__(self) -> None:
        self._by_account: dict[str, dict[str, _StoredEmail]] = {}
        self._account_to_user: dict[str, str] = {}

    def _seed(self, user_id: str, account_id: str, row: _StoredEmail) -> None:
        self._account_to_user[account_id] = user_id
        self._by_account.setdefault(account_id, {})[row.id] = row

    async def upsert_email(
        self,
        email_account_id: str,
        message: Any,
        attachments: Any = None,
        contact_id: str | None = None,
    ) -> Email:
        raise NotImplementedError

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
        return None

    async def get_by_message_id(
        self, user_id: str, message_id: str
    ) -> Email | None:
        return None

    async def mark_read(self, user_id: str, email_id: str) -> bool:
        return False

    async def search(
        self,
        user_id: str,
        account_id: str | None,
        query: str,
        limit: int,
    ) -> list[Email]:
        pattern = query.lower()
        eligible = {
            acc_id
            for acc_id, owner in self._account_to_user.items()
            if owner == user_id
        }
        if account_id is not None and account_id not in eligible:
            return []
        rows: list[_StoredEmail] = []
        for acc_id in eligible:
            if account_id is not None and acc_id != account_id:
                continue
            for row in self._by_account.get(acc_id, {}).values():
                rows.append(row)
        rows = [
            r
            for r in rows
            if (r.subject and pattern in r.subject.lower())
            or (r.body_text and pattern in r.body_text.lower())
            or pattern in r.from_address.lower()
        ]
        return [_to_email(r) for r in rows[:limit]]

    async def move_folder(self, user_id: str, email_id: str, folder: str) -> bool:
        return False


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
        body_html=None,
        body_text=row.body_text,
        is_read=False,
        is_starred=False,
        has_attachments=False,
        contact_id=None,
        received_at=row.received_at,
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


def _seed_row(
    *,
    user_id: str,
    account_id: str,
    subject: str,
    body_text: str,
    from_address: str,
    folder: str = "INBOX",
    received_at: datetime | None = None,
) -> _StoredEmail:
    return _StoredEmail(
        id=str(uuid.uuid4()),
        email_account_id=account_id,
        message_id=f"msg-{uuid.uuid4()}",
        folder=folder,
        from_address=from_address,
        to_addresses=["owner@example.com"],
        subject=subject,
        body_text=body_text,
        received_at=received_at or datetime(2026, 1, 1, tzinfo=UTC),
    )


# ===========================================================================
# REQ-003 scenario 1: termo em duas contas próprias → retorna das duas
# ===========================================================================


def test_search_returns_matches_across_own_accounts(
    client: TestClient, emails_repo: _FakeEmailRepository
) -> None:
    _as(_USER_A)
    account_a1 = "acc-a1"
    account_a2 = "acc-a2"
    base = datetime(2026, 1, 1, tzinfo=UTC)

    emails_repo._seed(
        "user-a",
        account_a1,
        _seed_row(
            user_id="user-a",
            account_id=account_a1,
            subject="needle in A1",
            body_text="",
            from_address="alice@example.com",
            received_at=base,
        ),
    )
    emails_repo._seed(
        "user-a",
        account_a2,
        _seed_row(
            user_id="user-a",
            account_id=account_a2,
            subject="needle in A2",
            body_text="",
            from_address="bob@example.com",
            received_at=base,
        ),
    )

    resp = client.get("/api/email/search", params={"q": "needle"})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    subjects = sorted(e["subject"] for e in body)
    assert subjects == ["needle in A1", "needle in A2"]
    assert {e["email_account_id"] for e in body} == {account_a1, account_a2}


# ===========================================================================
# REQ-003 scenario 2: termo só em emails de outro user → vazio
# ===========================================================================


def test_search_never_returns_another_users_data(
    client: TestClient, emails_repo: _FakeEmailRepository
) -> None:
    _as(_USER_A)
    base = datetime(2026, 1, 1, tzinfo=UTC)

    # user A: email sem o termo
    emails_repo._seed(
        "user-a",
        "acc-a1",
        _seed_row(
            user_id="user-a",
            account_id="acc-a1",
            subject="Unrelated",
            body_text="haystack",
            from_address="alice@example.com",
            received_at=base,
        ),
    )
    # user B: email COM o termo "needle" — não deve vazar para A
    emails_repo._seed(
        "user-b",
        "acc-b1",
        _seed_row(
            user_id="user-b",
            account_id="acc-b1",
            subject="needle here",
            body_text="",
            from_address="bob@example.com",
            received_at=base,
        ),
    )

    resp = client.get("/api/email/search", params={"q": "needle"})

    assert resp.status_code == 200, resp.text
    assert resp.json() == []


# ===========================================================================
# Validação: q vazio → 422
# ===========================================================================


def test_search_rejects_empty_query(
    client: TestClient, emails_repo: _FakeEmailRepository
) -> None:
    _as(_USER_A)

    resp = client.get("/api/email/search", params={"q": ""})

    assert resp.status_code == 422, resp.text


# ===========================================================================
# account_id filtra o escopo da busca
# ===========================================================================


def test_search_with_account_id_filters_scope(
    client: TestClient, emails_repo: _FakeEmailRepository
) -> None:
    _as(_USER_A)
    base = datetime(2026, 1, 1, tzinfo=UTC)
    account_a1 = "acc-a1"
    account_a2 = "acc-a2"

    emails_repo._seed(
        "user-a",
        account_a1,
        _seed_row(
            user_id="user-a",
            account_id=account_a1,
            subject="needle A1",
            body_text="",
            from_address="x@x.com",
            received_at=base,
        ),
    )
    emails_repo._seed(
        "user-a",
        account_a2,
        _seed_row(
            user_id="user-a",
            account_id=account_a2,
            subject="needle A2",
            body_text="",
            from_address="x@x.com",
            received_at=base,
        ),
    )

    resp = client.get(
        "/api/email/search",
        params={"q": "needle", "account_id": account_a1},
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body) == 1
    assert body[0]["subject"] == "needle A1"
    assert body[0]["email_account_id"] == account_a1
