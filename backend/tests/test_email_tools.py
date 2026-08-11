"""Testes de `src/tools/email_tools.py` (email-client-imap-mvp-task-tools-1).

Unit-1 (REQ-001 email-inbox): `list_emails`/`get_email_accounts` chamados numa
sessão resolvida para user A devolvem só dados do user A; `get_email_accounts`
nunca devolve credenciais descriptografadas (campo `imap_password`/`smtp_password`).

Mesmo padrão de `test_crm_tools.py` — `resolve_user_id()` é stubado por
monkeypatch e os repositórios são substituídos por fakes in-memory que
implementam a port interface. Nenhum Postgres real envolvido.
"""
from __future__ import annotations

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
from src.domain.email import Email, EmailAccount, EmailAccountStatus, ParsedAttachment

# ===========================================================================
# Fakes
# ===========================================================================


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
    received_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class _FakeEmailRepository(EmailRepositoryPort):
    """In-memory implementation do `EmailRepositoryPort` para os testes.

    Implementa o scoping por `user_id` igual à versão Postgres: rows são
    armazenados por `account_id`, e cada `account_id` é mapeado para um
    único `user_id`. Qualquer operação que recebe um `user_id` filtra
    através desse mapeamento, simulando a JOIN `emails → email_accounts`
    que existe em produção.
    """

    def __init__(self) -> None:
        self._by_account: dict[str, dict[str, _StoredEmail]] = {}
        self._account_to_user: dict[str, str] = {}
        self.list_by_account_calls: list[dict[str, Any]] = []

    def _seed(self, user_id: str, account_id: str, row: _StoredEmail) -> None:
        self._account_to_user[account_id] = user_id
        self._by_account.setdefault(account_id, {})[row.id] = row

    async def upsert_email(
        self,
        email_account_id: str,
        message: Any,
        attachments: list[ParsedAttachment] | None = None,
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
        self.list_by_account_calls.append(
            {"user_id": user_id, "account_id": account_id, "folder": folder}
        )
        # Scoping por user_id — só retorna rows de contas do `user_id`.
        eligible_account_ids = {
            acc_id
            for acc_id, owner in self._account_to_user.items()
            if owner == user_id
        }
        rows: list[_StoredEmail] = []
        for acc_id in eligible_account_ids:
            rows.extend(self._by_account.get(acc_id, {}).values())
        if account_id is not None:
            rows = [r for r in rows if r.email_account_id == account_id]
        if folder is not None:
            rows = [r for r in rows if r.folder == folder]
        rows.sort(key=lambda r: r.received_at, reverse=True)
        return [_to_email(r) for r in rows[offset : offset + limit]]

    async def get(self, user_id: str, email_id: str) -> Email | None:
        for rows_by_id in self._by_account.values():
            row = rows_by_id.get(email_id)
            if row is not None:
                return _to_email(row)
        return None

    async def get_by_message_id(
        self, user_id: str, message_id: str
    ) -> Email | None:
        for rows_by_id in self._by_account.values():
            for row in rows_by_id.values():
                if row.message_id == message_id:
                    return _to_email(row)
        return None

    async def mark_read(self, user_id: str, email_id: str) -> bool:
        for rows_by_id in self._by_account.values():
            if email_id in rows_by_id:
                rows_by_id[email_id].is_read = True  # type: ignore[attr-defined]
                return True
        return False

    async def search(
        self,
        user_id: str,
        account_id: str | None,
        query: str,
        limit: int,
    ) -> list[Email]:
        pattern = query.lower()
        rows: list[_StoredEmail] = []
        for rows_by_id in self._by_account.values():
            rows.extend(rows_by_id.values())
        rows = [
            r
            for r in rows
            if (r.subject and pattern in r.subject.lower())
            or (r.body_text and pattern in r.body_text.lower())
            or pattern in r.from_address.lower()
        ]
        return [_to_email(r) for r in rows[:limit]]

    async def move_folder(self, user_id: str, email_id: str, folder: str) -> bool:
        for rows_by_id in self._by_account.values():
            if email_id in rows_by_id:
                rows_by_id[email_id].folder = folder
                return True
        return False


class _FakeEmailAccountRepository(EmailAccountRepositoryPort):
    """In-memory implementation do `EmailAccountRepositoryPort` para os testes."""

    def __init__(self) -> None:
        self.accounts: dict[str, EmailAccount] = {}
        self.list_by_user_calls: list[str] = []

    def _seed(self, account: EmailAccount) -> None:
        self.accounts[account.id] = account

    async def create(self, account: EmailAccount) -> EmailAccount:
        self.accounts[account.id] = account
        return account

    async def get(self, user_id: str, account_id: str) -> EmailAccount | None:
        account = self.accounts.get(account_id)
        if account is None or account.user_id != user_id:
            return None
        return account

    async def list_by_user(self, user_id: str) -> list[EmailAccount]:
        self.list_by_user_calls.append(user_id)
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


# ===========================================================================
# Helpers
# ===========================================================================


def _stub_resolved_user_id(
    monkeypatch: pytest.MonkeyPatch, user_id: str | None
) -> None:
    """Faz `email_tools.resolve_user_id` devolver `user_id` (ou None)."""

    async def _fake_resolve_user_id() -> str | None:
        return user_id

    monkeypatch.setattr(et, "resolve_user_id", _fake_resolve_user_id)


def _seed_email(
    repo: _FakeEmailRepository,
    *,
    user_id: str,
    account_id: str,
    folder: str,
    subject: str,
    body_text: str,
    from_address: str,
    received_at: datetime,
) -> str:
    """Insere um email e devolve seu id."""
    email_id = str(uuid.uuid4())
    repo._seed(
        user_id,
        account_id,
        _StoredEmail(
            id=email_id,
            email_account_id=account_id,
            message_id=f"msg-{uuid.uuid4()}",
            folder=folder,
            from_address=from_address,
            to_addresses=["owner@example.com"],
            subject=subject,
            body_text=body_text,
            received_at=received_at,
        ),
    )
    return email_id


def _make_account(*, user_id: str, display_name: str) -> EmailAccount:
    return EmailAccount(
        id=str(uuid.uuid4()),
        user_id=user_id,
        user_integration_id=str(uuid.uuid4()),
        display_name=display_name,
        provider="imap",
        status=EmailAccountStatus.CONNECTED,
        is_active=True,
    )


# ===========================================================================
# unit-1: scoping + ausência de segredos
# ===========================================================================


async def test_list_emails_scopes_results_to_session_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`list_emails` chamado em sessão do user A só devolve emails das contas do A.

    REQ-001 (email-inbox): o tool `list_emails`, sob sessão resolvida como
    `user_id=A`, devolve apenas emails das contas próprias de A — nunca
    mistura emails de B mesmo que existam na mesma tabela.
    """
    session_user = "user-a"
    _stub_resolved_user_id(monkeypatch, session_user)

    emails_repo = _FakeEmailRepository()
    accounts_repo = _FakeEmailAccountRepository()

    # user A — 1 conta, 1 email em INBOX
    account_a = _make_account(user_id=session_user, display_name="A IMAP")
    accounts_repo._seed(account_a)
    email_a_id = _seed_email(
        emails_repo,
        user_id=session_user,
        account_id=account_a.id,
        folder="INBOX",
        subject="A's message",
        body_text="for user A",
        from_address="alice@example.com",
        received_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    # user B — 1 conta, 1 email em INBOX (não deve aparecer)
    account_b = _make_account(user_id="user-b", display_name="B IMAP")
    accounts_repo._seed(account_b)
    _seed_email(
        emails_repo,
        user_id="user-b",
        account_id=account_b.id,
        folder="INBOX",
        subject="B's message",
        body_text="for user B",
        from_address="bob@example.com",
        received_at=datetime(2026, 1, 2, tzinfo=UTC),
    )

    monkeypatch.setattr(et, "_email_repository", lambda: emails_repo)
    monkeypatch.setattr(et, "_email_account_repository", lambda: accounts_repo)
    monkeypatch.setattr(et, "_integration_repository", lambda: None)

    # Cenário REQ-001 unified: sem `account_id`, o tool lista emails de TODAS
    # as contas do user da sessão.
    result = await et.list_emails.ainvoke({})

    assert isinstance(result, dict)
    assert "emails" in result
    returned_ids = {e["id"] for e in result["emails"]}
    assert email_a_id in returned_ids
    # B's email nunca pode aparecer — `user_id` da sessão foi o anchor.
    assert not any(e["subject"] == "B's message" for e in result["emails"])
    # A sessão foi o anchor — `user_id` injetado via `resolve_user_id`.
    assert any(
        call["user_id"] == session_user for call in emails_repo.list_by_account_calls
    )


async def test_get_email_accounts_scopes_to_session_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`get_email_accounts` em sessão do user A só devolve contas do A.

    REQ-001 (email-account-management): o tool só lista contas próprias do
    usuário resolvido pela sessão — contas de B são omitidas.
    """
    session_user = "user-a"
    _stub_resolved_user_id(monkeypatch, session_user)

    accounts_repo = _FakeEmailAccountRepository()
    account_a = _make_account(user_id=session_user, display_name="A IMAP")
    account_b = _make_account(user_id="user-b", display_name="B IMAP")
    accounts_repo._seed(account_a)
    accounts_repo._seed(account_b)

    emails_repo = _FakeEmailRepository()
    monkeypatch.setattr(et, "_email_repository", lambda: emails_repo)
    monkeypatch.setattr(et, "_email_account_repository", lambda: accounts_repo)
    monkeypatch.setattr(et, "_integration_repository", lambda: None)

    result = await et.get_email_accounts.ainvoke({})

    assert isinstance(result, dict)
    assert "accounts" in result
    assert {a["id"] for a in result["accounts"]} == {account_a.id}
    assert account_b.id not in {a["id"] for a in result["accounts"]}
    # A sessão foi o anchor de scoping — `list_by_user` foi chamado com o user da sessão.
    assert accounts_repo.list_by_user_calls == [session_user]


async def test_get_email_accounts_never_leaks_decrypted_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`get_email_accounts` NUNCA devolve segredos descriptografados.

    REQ-001 (email-account-management): o tool só devolve metadata da conta
    (`id`, `display_name`, `provider`, `status`, `is_active`, `last_synced_at`).
    As credenciais IMAP/SMTP vivem cifradas em `user_integrations` e nunca
    devem aparecer em nenhuma chave do dict retornado — nem como texto claro,
    nem como cifra. Defesa em profundidade contra vazamento futuro do lado
    do serializador.
    """
    session_user = "user-a"
    _stub_resolved_user_id(monkeypatch, session_user)

    accounts_repo = _FakeEmailAccountRepository()
    account_a = _make_account(user_id=session_user, display_name="A IMAP")
    accounts_repo._seed(account_a)

    emails_repo = _FakeEmailRepository()
    monkeypatch.setattr(et, "_email_repository", lambda: emails_repo)
    monkeypatch.setattr(et, "_email_account_repository", lambda: accounts_repo)
    monkeypatch.setattr(et, "_integration_repository", lambda: None)

    result = await et.get_email_accounts.ainvoke({})

    forbidden_substrings = (
        "imap_password",
        "smtp_password",
        "imap_username",
        "smtp_username",
        "imap_host",
        "smtp_host",
        "gAAAAA",  # prefixo Fernet — garante que cifras também vazaram
    )

    def _assert_no_secrets(value: Any, path: str) -> None:
        if isinstance(value, dict):
            for key, sub in value.items():
                assert not any(s in key for s in forbidden_substrings), (
                    f"chave proibida em {path}: {key!r}"
                )
                _assert_no_secrets(sub, f"{path}.{key}")
        elif isinstance(value, list):
            for idx, sub in enumerate(value):
                _assert_no_secrets(sub, f"{path}[{idx}]")
        elif isinstance(value, str):
            assert not any(s in value for s in forbidden_substrings), (
                f"valor proibido em {path}: {value!r}"
            )

    _assert_no_secrets(result, "result")

    # A conta A continua presente, mas só com metadata pública.
    assert len(result["accounts"]) == 1
    assert result["accounts"][0]["id"] == account_a.id
    assert result["accounts"][0]["display_name"] == "A IMAP"


async def test_list_emails_without_identity_does_not_query_repo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sem `user_id` resolvível: erro e nenhum repo é consultado."""
    _stub_resolved_user_id(monkeypatch, None)

    emails_repo = _FakeEmailRepository()
    accounts_repo = _FakeEmailAccountRepository()

    monkeypatch.setattr(et, "_email_repository", lambda: emails_repo)
    monkeypatch.setattr(et, "_email_account_repository", lambda: accounts_repo)
    monkeypatch.setattr(et, "_integration_repository", lambda: None)

    result = await et.list_emails.ainvoke({"account_id": "any"})

    assert isinstance(result, dict)
    assert "error" in result
    assert emails_repo.list_by_account_calls == []
