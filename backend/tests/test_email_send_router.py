"""Testes de `POST /api/email/send` (task `email-client-imap-mvp-task-send-2`).

Cobre o unit-test linkado à task no OpenSddRag:

- unit-1 (REQ-005): GIVEN um usuário autenticado e seu próprio `account_id`,
  WHEN posted com body válido, THEN resposta 201 e `SendEmail.execute`
  chamado uma vez com os args casando. GIVEN `account_id` pertence a
  outro usuário, WHEN posted, THEN resposta de erro e `SendEmail.execute`
  nunca é chamado.

Mesmo padrão de `test_email_router.py` / `test_email_inbox_router.py`:
repositórios fakes via `dependency_overrides` + monkeypatch do
`SendEmail` para evitar SMTP/rede de verdade.
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
_USER_B = User(
    id="user-b",
    username="bob",
    password_hash="h",
    role="user",
    is_active=True,
    created_at=datetime(2026, 1, 1, tzinfo=UTC),
)


# ===========================================================================
# Fakes — accounts / integrations / emails
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


@dataclass
class _StoredEmail:
    """Replica mínima do `Email` para o repo fake — não usado pelo /send,
    mas mantido para satisfazer a port sem NotImplementedError."""

    id: str
    email_account_id: str
    message_id: str
    folder: str
    from_address: str
    to_addresses: list[str]
    subject: str | None
    received_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class _FakeEmailRepository(EmailRepositoryPort):
    """Suficiente para satisfazer a port — o /send não exercita nenhum método."""

    def __init__(self) -> None:
        self._store: dict[tuple[str, str], _StoredEmail] = {}

    async def upsert_email(
        self,
        email_account_id: str,
        message: Any,
        attachments: Any = None,
        contact_id: str | None = None,
    ) -> Any:
        raise NotImplementedError

    async def list_by_account(
        self,
        user_id: str,
        account_id: str | None = None,
        folder: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[Any]:
        return []

    async def get(self, user_id: str, email_id: str) -> Any:
        self._store.get((user_id, email_id))
        return None

    async def get_by_message_id(self, user_id: str, message_id: str) -> Any:
        return None

    async def mark_read(self, user_id: str, email_id: str) -> bool:
        return False

    async def search(
        self,
        user_id: str,
        account_id: str | None,
        query: str,
        limit: int,
    ) -> list[Any]:
        return []

    async def move_folder(self, user_id: str, email_id: str, folder: str) -> bool:
        return False


# ===========================================================================
# Fake SendEmail — substitui o use case real sem tocar em SMTP/rede
# ===========================================================================


@dataclass
class _FakeCallRecord:
    """Registro de uma chamada a `SendEmail.execute`."""

    user_id: str
    account_id: str
    to_addresses: list[str]
    cc_addresses: list[str] | None
    bcc_addresses: list[str] | None
    subject: str
    body_text: str
    body_html: str | None
    in_reply_to: str | None
    references: str | None


class _FakeSendEmail:
    """Substitui `src.application.use_cases.send_email.SendEmail`.

    O router importa `SendEmail` no nível do módulo (`from … import SendEmail`),
    então monkeypatchamos o símbolo dentro do módulo `email_router`.

    IMPORTANTE: para espelhar a guarda de ownership do use case real, este
    fake consulta `_FakeEmailAccountRepository.get(user_id, account_id)`
    antes de retornar sucesso. Se a conta não existe ou pertence a outro
    user, levanta `ValueError("Email account not found")` — exatamente
    como o `SendEmail.execute` real faz. Sem essa guarda, o teste não
    exercita o caminho de rejeição cross-user que o router precisa
    propagar como erro HTTP.
    """

    instances: list["_FakeSendEmail"] = []

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.calls: list[_FakeCallRecord] = []
        # Se o caller quiser forçar uma exceção adicional
        # (ex.: simular `SmtpAuthError`), basta setar
        # `self.raise_on_next_call` antes da próxima `.execute()`.
        self.raise_on_next_call: Exception | None = None
        _FakeSendEmail.instances.append(self)

    async def execute(
        self,
        *,
        user_id: str,
        account_id: str,
        to_addresses: list[str],
        subject: str,
        body_text: str,
        body_html: str | None = None,
        cc_addresses: list[str] | None = None,
        bcc_addresses: list[str] | None = None,
        in_reply_to: str | None = None,
        references: str | None = None,
        attachments: Any = None,
    ) -> Any:
        from src.application.use_cases.send_email import SendEmailResult

        # Guarda de ownership — espelha `SendEmail.execute` real.
        account_repo: _FakeEmailAccountRepository = self.kwargs["email_account_repository"]
        account = await account_repo.get(user_id, account_id)
        if account is None:
            raise ValueError("Email account not found")
        # (Não validamos a integration nem disparamos SMTP — fora do escopo do router.)

        self.calls.append(
            _FakeCallRecord(
                user_id=user_id,
                account_id=account_id,
                to_addresses=list(to_addresses),
                cc_addresses=list(cc_addresses) if cc_addresses else None,
                bcc_addresses=list(bcc_addresses) if bcc_addresses else None,
                subject=subject,
                body_text=body_text,
                body_html=body_html,
                in_reply_to=in_reply_to,
                references=references,
            )
        )
        if self.raise_on_next_call is not None:
            exc = self.raise_on_next_call
            self.raise_on_next_call = None
            raise exc
        return SendEmailResult(
            message_id=f"msg-{uuid.uuid4()}",
            sent_at=datetime.now(UTC),
            thread_id=None,
        )


# ===========================================================================
# Fixtures
# ===========================================================================


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
    webapp.app.dependency_overrides[email_router._email_repository] = (
        lambda: emails_repo
    )
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
    """Insere uma conta de email fake para `user_id` e devolve o ID."""
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


# ===========================================================================
# unit-1 (REQ-005): POST /api/email/send
# ===========================================================================


def test_send_email_happy_path_calls_use_case_with_matching_args(
    client: TestClient,
    accounts_repo: _FakeEmailAccountRepository,
) -> None:
    """Autenticado como user-a, com conta própria → 201 e SendEmail.execute
    chamado uma vez com os mesmos args do body."""
    _as(_USER_A)
    account_id = _seed_account(accounts_repo, user_id=_USER_A.id)

    body = {
        "account_id": account_id,
        "to_addresses": ["alice@example.com", "bob@example.com"],
        "subject": "Hello",
        "body_text": "Body content",
        "body_html": "<p>Body content</p>",
        "cc_addresses": ["cc@example.com"],
        "bcc_addresses": [],
        "in_reply_to": None,
        "references": None,
    }

    resp = client.post("/api/email/send", json=body)

    assert resp.status_code == 201, resp.text
    resp_body = resp.json()
    assert resp_body["message_id"]
    assert resp_body["subject"] == "Hello"
    # thread_id é null quando não é reply — não vem vazio na resposta.
    assert "thread_id" in resp_body

    # Houve exatamente UMA chamada, com os args casando.
    assert len(_FakeSendEmail.instances) == 1
    fake = _FakeSendEmail.instances[0]
    assert len(fake.calls) == 1
    call = fake.calls[0]
    assert call.user_id == _USER_A.id
    assert call.account_id == account_id
    assert call.to_addresses == ["alice@example.com", "bob@example.com"]
    assert call.cc_addresses == ["cc@example.com"]
    assert call.subject == "Hello"
    assert call.body_text == "Body content"
    assert call.body_html == "<p>Body content</p>"


def test_send_email_rejects_account_owned_by_other_user(
    client: TestClient,
    accounts_repo: _FakeEmailAccountRepository,
) -> None:
    """User-a tentando enviar pela conta de user-b → erro, e SendEmail.execute
    nunca é chamado. Defesa em profundidade: o use case também checa (ele
    levanta `ValueError("Email account not found")` ao buscar com o user
    errado), mas a rota deve refletir isso num status de erro."""
    _as(_USER_A)
    # Conta pertence a user-b, não a user-a.
    account_id = _seed_account(accounts_repo, user_id=_USER_B.id)

    body = {
        "account_id": account_id,
        "to_addresses": ["x@example.com"],
        "subject": "Stolen",
        "body_text": "Body",
    }

    resp = client.post("/api/email/send", json=body)

    # O endpoint converte `ValueError` em 404 (a conta não é "encontrada"
    # para o user errado — não revela se existe). 404 é defensável; 403 também.
    assert resp.status_code in (403, 404), resp.text

    # SendEmail NUNCA registrou uma chamada bem-sucedida (pode ter sido
    # instanciado, mas o `.execute()` falhou antes do append em `self.calls`).
    total_calls = sum(len(inst.calls) for inst in _FakeSendEmail.instances)
    assert total_calls == 0


def test_send_email_rejects_when_account_does_not_exist(
    client: TestClient,
    accounts_repo: _FakeEmailAccountRepository,
) -> None:
    """account_id inexistente → erro sem dispatch."""
    _as(_USER_A)

    body = {
        "account_id": "no-such-account",
        "to_addresses": ["x@example.com"],
        "subject": "Nope",
        "body_text": "Body",
    }

    resp = client.post("/api/email/send", json=body)

    assert resp.status_code == 404, resp.text
    total_calls = sum(len(inst.calls) for inst in _FakeSendEmail.instances)
    assert total_calls == 0


def test_send_email_rejects_empty_to_addresses(
    client: TestClient,
    accounts_repo: _FakeEmailAccountRepository,
) -> None:
    """`to_addresses` vazio → 422 sem chamar o use case."""
    _as(_USER_A)
    account_id = _seed_account(accounts_repo, user_id=_USER_A.id)

    body = {
        "account_id": account_id,
        "to_addresses": [],
        "subject": "Nobody",
        "body_text": "Body",
    }

    resp = client.post("/api/email/send", json=body)

    assert resp.status_code == 422, resp.text
    total_calls = sum(len(inst.calls) for inst in _FakeSendEmail.instances)
    assert total_calls == 0
