"""Testes dos use cases de inbox de email (email-client-imap-mvp-task-inbox-1).

Cobre os 2 unit-tests linkados à task no OpenSddRag:

- unit-1 (REQ-001): `ListEmails` sem filtros retorna emails de todas as contas
  do user, ordenado por `received_at` DESC; com `account_id`+`folder` retorna
  só as linhas que casam.
- unit-2 (REQ-002/REQ-003): `GetEmail` retorna o body e marca `is_read=True`
  como efeito colateral; `GetEmail` cross-user retorna None; `SearchEmails`
  restringe a busca às contas do próprio user (resultado vazio quando o termo
  só aparece em emails de outro user).

Mesmo padrão de `test_email_account_use_cases.py` — repositório é fake
injetado no use case, sem Postgres real.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from src.application.ports.email_repository import EmailRepositoryPort
from src.domain.email import Email


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
    is_read: bool = False
    received_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class _FakeEmailRepository(EmailRepositoryPort):
    """In-memory implementation do `EmailRepositoryPort` para os testes."""

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
        for row in self._by_user.get(user_id, {}).values():
            if row.message_id == message_id:
                return _to_email(row)
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
        pattern = query.lower()
        rows = list(self._by_user.get(user_id, {}).values())
        if account_id is not None:
            rows = [r for r in rows if r.email_account_id == account_id]
        rows = [
            r
            for r in rows
            if (r.subject and pattern in r.subject.lower())
            or (r.body_text and pattern in r.body_text.lower())
            or pattern in r.from_address.lower()
        ]
        rows.sort(key=lambda r: r.received_at, reverse=True)
        return [_to_email(r) for r in rows[:limit]]

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
        body_html=None,
        body_text=row.body_text,
        is_read=row.is_read,
        is_starred=False,
        has_attachments=False,
        contact_id=None,
        received_at=row.received_at,
    )


def _build_row(
    user_id: str,
    *,
    account_id: str,
    folder: str,
    subject: str,
    body_text: str,
    from_address: str,
    received_at: datetime,
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
        received_at=received_at,
    )


# ===========================================================================
# unit-1 (REQ-001): listagem unificada e filtrada, escopada ao user
# ===========================================================================


async def test_list_emails_without_filters_returns_all_users_emails_sorted_desc() -> None:
    from src.application.use_cases.list_emails import ListEmails

    repo = _FakeEmailRepository()
    user_a = "user-a"
    user_b = "user-b"
    account_a1 = "acc-a1"
    account_a2 = "acc-a2"
    account_b = "acc-b"

    base = datetime(2026, 1, 1, tzinfo=UTC)
    repo._add(
        user_a,
        _build_row(
            user_a,
            account_id=account_a1,
            folder="INBOX",
            subject="A1 Inbox old",
            body_text="",
            from_address="alice@example.com",
            received_at=base,
        ),
    )
    repo._add(
        user_a,
        _build_row(
            user_a,
            account_id=account_a2,
            folder="INBOX",
            subject="A2 Inbox mid",
            body_text="",
            from_address="bob@example.com",
            received_at=base + timedelta(hours=1),
        ),
    )
    repo._add(
        user_a,
        _build_row(
            user_a,
            account_id=account_a1,
            folder="Sent",
            subject="A1 Sent newest",
            body_text="",
            from_address="carol@example.com",
            received_at=base + timedelta(hours=2),
        ),
    )
    repo._add(
        user_b,
        _build_row(
            user_b,
            account_id=account_b,
            folder="INBOX",
            subject="B Inbox should be hidden",
            body_text="",
            from_address="dave@example.com",
            received_at=base + timedelta(hours=3),
        ),
    )

    result = await ListEmails(repository=repo).execute(user_id=user_a, limit=10, offset=0)

    assert len(result.items) == 3
    # received_at DESC: A1 Sent (h+2) > A2 Inbox (h+1) > A1 Inbox (h+0).
    assert [item.subject for item in result.items] == [
        "A1 Sent newest",
        "A2 Inbox mid",
        "A1 Inbox old",
    ]
    assert {item.email_account_id for item in result.items} == {account_a1, account_a2}


async def test_list_emails_with_account_id_and_folder_filters_results() -> None:
    from src.application.use_cases.list_emails import ListEmails

    repo = _FakeEmailRepository()
    user_a = "user-a"
    account_a1 = "acc-a1"
    account_a2 = "acc-a2"
    base = datetime(2026, 1, 1, tzinfo=UTC)

    repo._add(
        user_a,
        _build_row(
            user_a,
            account_id=account_a1,
            folder="INBOX",
            subject="A1 Inbox",
            body_text="",
            from_address="alice@example.com",
            received_at=base,
        ),
    )
    repo._add(
        user_a,
        _build_row(
            user_a,
            account_id=account_a1,
            folder="Sent",
            subject="A1 Sent",
            body_text="",
            from_address="bob@example.com",
            received_at=base + timedelta(hours=1),
        ),
    )
    repo._add(
        user_a,
        _build_row(
            user_a,
            account_id=account_a2,
            folder="Sent",
            subject="A2 Sent (other account)",
            body_text="",
            from_address="carol@example.com",
            received_at=base + timedelta(hours=2),
        ),
    )

    result = await ListEmails(repository=repo).execute(
        user_id=user_a, account_id=account_a1, folder="Sent", limit=10, offset=0
    )

    assert [item.subject for item in result.items] == ["A1 Sent"]
    assert result.account_id == account_a1
    assert result.folder == "Sent"


# ===========================================================================
# unit-2 (REQ-002/REQ-003): get_email marca lido e rejeita cross-user;
# search_emails não vaza dados de outro user
# ===========================================================================


async def test_get_email_returns_body_and_marks_as_read() -> None:
    from src.application.use_cases.get_email import GetEmail

    repo = _FakeEmailRepository()
    user_a = "user-a"
    account = "acc-a1"
    row = _build_row(
        user_a,
        account_id=account,
        folder="INBOX",
        subject="Subject",
        body_text="body content",
        from_address="sender@example.com",
        received_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    repo._add(user_a, row)

    assert row.is_read is False

    email = await GetEmail(repository=repo).execute(user_id=user_a, email_id=row.id)

    assert email is not None
    assert email.subject == "Subject"
    assert email.body_text == "body content"
    # Side effect: row flipped to read in storage.
    assert row.is_read is True


async def test_get_email_for_other_users_email_returns_none() -> None:
    from src.application.use_cases.get_email import GetEmail

    repo = _FakeEmailRepository()
    user_a = "user-a"
    user_b = "user-b"
    account = "acc-a1"
    row = _build_row(
        user_a,
        account_id=account,
        folder="INBOX",
        subject="Private",
        body_text="",
        from_address="sender@example.com",
        received_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    repo._add(user_a, row)

    email = await GetEmail(repository=repo).execute(user_id=user_b, email_id=row.id)

    assert email is None
    # Cross-user attempt must not have flipped the flag as a side effect.
    assert row.is_read is False


async def test_search_emails_never_returns_another_users_data() -> None:
    from src.application.use_cases.search_emails import SearchEmails

    repo = _FakeEmailRepository()
    user_a = "user-a"
    user_b = "user-b"
    account_a = "acc-a1"
    account_b = "acc-b1"
    base = datetime(2026, 1, 1, tzinfo=UTC)

    # Term "needle" exists ONLY in user B's emails.
    repo._add(
        user_a,
        _build_row(
            user_a,
            account_id=account_a,
            folder="INBOX",
            subject="Unrelated",
            body_text="haystack",
            from_address="alice@example.com",
            received_at=base,
        ),
    )
    repo._add(
        user_b,
        _build_row(
            user_b,
            account_id=account_b,
            folder="INBOX",
            subject="needle here",
            body_text="",
            from_address="bob@example.com",
            received_at=base,
        ),
    )

    result = await SearchEmails(repository=repo).execute(
        user_id=user_a, query="needle", limit=10
    )

    assert result.items == []
