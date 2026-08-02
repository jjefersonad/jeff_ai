"""Testes de `attachments_router` — autenticação global (chat-file-attachment REQ-002).

Testa a dependency `require_auth` GLOBAL real (sem override), como
`test_webapp_global_auth.py`, mas focado em `POST /api/attachments`. Mocka
`store_attachment` para não tocar Postgres/disco real — persistência já é
coberta por `test_attachment_store.py`; este arquivo cobre só autenticação.
"""
from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient

import src.infrastructure.web.attachments_router as attachments_router
import src.infrastructure.web.webapp as webapp
from src.infrastructure.attachments.store import StoredAttachment
from src.infrastructure.auth import session_resolver
from src.infrastructure.auth.sessions import Session
from src.infrastructure.auth.users import User

_VALID_SESSION = Session(token="tok-valid", user_id="user-1", expires_at=None)  # type: ignore[arg-type]
_VALID_USER = User(id="user-1", username="alice", password_hash="h", role="user", is_active=True)

_PDF_BYTES = b"%PDF-1.4 fake pdf bytes"


@pytest.fixture
def client() -> TestClient:
    return TestClient(webapp.app)


def _allow_valid_session(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_get_session(token: str) -> Session | None:
        return _VALID_SESSION if token == "tok-valid" else None

    async def _fake_get_user_by_id(user_id: str) -> User | None:
        return _VALID_USER if user_id == "user-1" else None

    monkeypatch.setattr(session_resolver, "get_session", _fake_get_session)
    monkeypatch.setattr(session_resolver, "get_user_by_id", _fake_get_user_by_id)


def _fake_store_attachment(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    calls: list[dict] = []

    async def _fake(**kwargs: object) -> StoredAttachment:
        calls.append(kwargs)
        return StoredAttachment(
            attachment_id="att-1",
            thread_id=kwargs["thread_id"],  # type: ignore[arg-type]
            filename=kwargs["filename"],  # type: ignore[arg-type]
            content_type=kwargs["content_type"],  # type: ignore[arg-type]
            size_bytes=len(kwargs["data"]),  # type: ignore[arg-type]
            storage_path="/tmp/att-1.pdf",
        )

    monkeypatch.setattr(attachments_router, "store_attachment", _fake)
    return calls


def test_upload_attachment_requires_auth_by_default(client: TestClient) -> None:
    """REQ-002: sem cookie de sessão, 401 — herdado da dependency global."""
    resp = client.post(
        "/api/attachments",
        data={"thread_id": "thread-1"},
        files={"file": ("report.pdf", io.BytesIO(_PDF_BYTES), "application/pdf")},
    )
    assert resp.status_code == 401


def test_upload_attachment_rejects_unauthenticated_without_persisting(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    """REQ-002: request sem sessão válida não persiste nada."""
    calls = _fake_store_attachment(monkeypatch)

    resp = client.post(
        "/api/attachments",
        data={"thread_id": "thread-1"},
        files={"file": ("report.pdf", io.BytesIO(_PDF_BYTES), "application/pdf")},
    )

    assert resp.status_code == 401
    assert calls == []


def test_upload_attachment_accepts_valid_session_cookie(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    """REQ-002: sessão válida não é bloqueada por 401 e chega à persistência."""
    _allow_valid_session(monkeypatch)
    calls = _fake_store_attachment(monkeypatch)
    client.cookies.set("session", "tok-valid")

    resp = client.post(
        "/api/attachments",
        data={"thread_id": "thread-1"},
        files={"file": ("report.pdf", io.BytesIO(_PDF_BYTES), "application/pdf")},
    )

    assert resp.status_code == 200, resp.text
    assert len(calls) == 1
    assert calls[0]["thread_id"] == "thread-1"
    assert calls[0]["user_id"] == "user-1"
