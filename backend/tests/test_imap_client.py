"""Testes de `src/infrastructure/email/imap_client.py`.

Unit-1 (email-client-imap-mvp-task-accounts-2, REQ-001 email-account-management):
`verify_imap_login` distingue login recusado (`ImapAuthError`) de sucesso, sem
nunca vazar a senha em texto puro na mensagem de erro.

Unit-1/2 (email-client-imap-mvp-task-sync-1):
- `fetch_new_messages` retorna apenas mensagens com UID acima do watermark
  (REQ-005 email-account-management).
- `sanitize_body_html` remove `<script>` e handlers inline antes de qualquer
  persistência (REQ-002 email-inbox).
"""
from __future__ import annotations

from collections import namedtuple
from datetime import UTC, datetime

import aioimaplib
import pytest

from src.application.integrations.config_schemas import (
    GmailIntegrationConfig,
    ImapIntegrationConfig,
)
from src.infrastructure.email.imap_client import (
    ImapAuthError,
    fetch_new_messages,
    sanitize_body_html,
    verify_imap_login,
)

_Response = namedtuple("_Response", "result lines")

_CONFIG = ImapIntegrationConfig(
    imap_host="imap.example.com",
    imap_port=993,
    imap_username="user@example.com",
    imap_password="s3cr3t-password",
    smtp_host="smtp.example.com",
    smtp_port=587,
)

_GMAIL_CONFIG = GmailIntegrationConfig(
    email_address="user@gmail.com",
    access_token="ya29.access",
    refresh_token="1//refresh",
    token_expiry=datetime.now(UTC),
)


class _FakeImapClient:
    def __init__(self, *, login_result: str) -> None:
        self._login_result = login_result
        self.logged_out = False

    async def wait_hello_from_server(self) -> None:
        return None

    async def login(self, user: str, password: str) -> _Response:
        return _Response(self._login_result, [])

    async def logout(self) -> None:
        self.logged_out = True


async def test_verify_imap_login_succeeds_with_valid_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client = _FakeImapClient(login_result="OK")
    monkeypatch.setattr(
        aioimaplib, "IMAP4_SSL", lambda **kwargs: fake_client
    )

    await verify_imap_login(_CONFIG)

    assert fake_client.logged_out is True


async def test_verify_imap_login_raises_imap_auth_error_on_bad_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client = _FakeImapClient(login_result="NO")
    monkeypatch.setattr(
        aioimaplib, "IMAP4_SSL", lambda **kwargs: fake_client
    )

    with pytest.raises(ImapAuthError) as exc_info:
        await verify_imap_login(_CONFIG)

    # ImapAuthError is its own type — never conflated with a generic
    # connection/timeout error (OSError/TimeoutError family).
    assert not isinstance(exc_info.value, (OSError, TimeoutError))
    assert "s3cr3t-password" not in str(exc_info.value)


def _raw_message(*, subject: str, body: str = "corpo") -> bytes:
    return (
        f"From: Alice <alice@example.com>\r\n"
        f"To: bob@example.com\r\n"
        f"Subject: {subject}\r\n"
        f"Message-ID: <{subject.lower().replace(' ', '-')}@example.com>\r\n"
        f"Content-Type: text/plain; charset=utf-8\r\n"
        f"\r\n"
        f"{body}\r\n"
    ).encode()


class _FakeImapServer:
    """Simula um servidor IMAP real: `search` filtra por UID, `fetch` devolve bytes RFC822."""

    def __init__(self, messages: dict[int, bytes]) -> None:
        self._messages = messages
        self.logged_out = False
        self.login_calls: list[tuple[str, str]] = []
        self.xoauth2_calls: list[tuple[str, bytes]] = []

    async def wait_hello_from_server(self) -> None:
        return None

    async def login(self, user: str, password: str) -> _Response:
        self.login_calls.append((user, password))
        return _Response("OK", [])

    async def xoauth2(self, user: str, token: bytes) -> _Response:
        self.xoauth2_calls.append((user, token))
        return _Response("OK", [])

    async def select(self, folder: str) -> _Response:
        return _Response("OK", [])

    async def search(
        self, *criteria: str, charset: str | None = "utf-8", by_uid: bool = False
    ) -> _Response:
        # Sem o `by_uid=True`, é uma busca por sequence number — não é o
        # que `fetch_new_messages` usa. Mantido aqui só para paridade com
        # a API real; o caminho de produção é `uid_search`.
        return _Response("OK", [b""])

    async def uid_search(
        self, *criteria: str, charset: str | None = "utf-8"
    ) -> _Response:
        # `criteria[-1]` é algo como "UID 101:*" — o `uid_search` da
        # `aioimaplib` recebe os critérios JÁ com o `UID` keyword e
        # adiciona o prefixo `UID` na frente do comando SEARCH.
        start = int(criteria[-1].split()[-1].split(":")[0])
        uids = sorted(uid for uid in self._messages if uid >= start)
        # Real aioimaplib devolve a keyword do comando como primeiro
        # token (`b"SEARCH 1 2 3"`), após remover o prefixo `* `.
        return _Response(
            "OK",
            [b"SEARCH " + " ".join(str(uid) for uid in uids).encode()],
        )

    async def uid(self, command: str, *criteria: str) -> _Response:
        if command == "fetch":
            uid = int(criteria[0])
            raw = self._messages[uid]
            return _Response(
                "OK",
                [f"{uid} FETCH (UID {uid} RFC822 {{{len(raw)}}}".encode(), raw, b")"],
            )
        raise ValueError(f"comando UID não simulado: {command!r}")

    async def logout(self) -> None:
        self.logged_out = True


async def test_fetch_new_messages_returns_only_messages_newer_than_watermark(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = _FakeImapServer(
        {
            100: _raw_message(subject="Old"),
            101: _raw_message(subject="New One"),
            102: _raw_message(subject="New Two"),
        }
    )
    monkeypatch.setattr(aioimaplib, "IMAP4_SSL", lambda **kwargs: server)

    messages = await fetch_new_messages(_CONFIG, folder="INBOX", watermark=100)

    assert {message.subject for message in messages} == {"New One", "New Two"}
    assert server.logged_out is True


async def test_fetch_new_messages_with_gmail_config_uses_xoauth2(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """gmail-account-oauth-connection-task-sync-1-unit-1 (REQ-003)."""
    server = _FakeImapServer({101: _raw_message(subject="New One")})
    monkeypatch.setattr(aioimaplib, "IMAP4_SSL", lambda **kwargs: server)

    await fetch_new_messages(_GMAIL_CONFIG, folder="INBOX", watermark=100)

    assert server.xoauth2_calls == [("user@gmail.com", b"ya29.access")]
    assert server.login_calls == []


async def test_fetch_new_messages_with_imap_config_still_uses_login(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """gmail-account-oauth-connection-task-sync-1-unit-2 (REQ-003) — regressão."""
    server = _FakeImapServer({101: _raw_message(subject="New One")})
    monkeypatch.setattr(aioimaplib, "IMAP4_SSL", lambda **kwargs: server)

    await fetch_new_messages(_CONFIG, folder="INBOX", watermark=100)

    assert server.login_calls == [("user@example.com", "s3cr3t-password")]
    assert server.xoauth2_calls == []


async def test_extract_search_uids_strips_keyword_and_handles_empty() -> None:
    """Cobre a regressão 2026-08-10: aioimaplib devolve `b"SEARCH 1 2 3"`
    (keyword do comando ainda presente) e o split bruto levantava
    `ValueError` em `int(b"SEARCH")`, marcando a conta como `error` no
    sync worker sem persistir nenhuma mensagem.
    """
    from src.infrastructure.email.imap_client import _extract_search_uids

    # Caso típico: keyword + UIDs.
    assert _extract_search_uids([b"SEARCH 101 102 103"]) == [101, 102, 103]
    # Resposta vazia (sem mensagens novas).
    assert _extract_search_uids([b"SEARCH"]) == []
    assert _extract_search_uids([]) == []
    # Múltiplas linhas (servidores quebram resposta grande).
    assert _extract_search_uids([b"SEARCH 1 2", b"3 4 5"]) == [1, 2, 3, 4, 5]


async def test_sanitize_body_html_strips_script_and_event_handlers() -> None:
    raw_html = (
        '<p>Hello <script>alert(1)</script>'
        '<a href="https://example.com" onclick="evil()">link</a></p>'
    )

    sanitized = sanitize_body_html(raw_html)

    assert "<script>" not in sanitized
    assert "onclick" not in sanitized
    assert "<p>" in sanitized
    assert '<a href="https://example.com"' in sanitized
