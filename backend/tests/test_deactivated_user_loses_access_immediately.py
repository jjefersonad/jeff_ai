"""Teste de integração: usuário desativado perde acesso na requisição seguinte
(change `user-management`, task-api-5, REQ-005).

Sem código de produto novo — `resolve_session_user` já checa `is_active` a
cada requisição (`session_resolver.py:70`), lendo o usuário do banco a cada
chamada em vez de cachear. Este teste só prova, ponta a ponta contra
`webapp.app`, que uma mudança de `is_active` (como a que `PATCH
/admin/users/{id}` faz via `update_user`) derruba o acesso do usuário na
PRÓXIMA requisição autenticada, sem exigir logout ou revogação explícita de
sessão — mesmo padrão de mock de `session_resolver.get_session`/
`get_user_by_id` já usado por `test_webapp_global_auth.py`.
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

import src.infrastructure.web.webapp as webapp
from src.infrastructure.auth import session_resolver
from src.infrastructure.auth.sessions import Session
from src.infrastructure.auth.users import User

_SESSION = Session(token="tok-user", user_id="user-1", expires_at=None)  # type: ignore[arg-type]


@pytest.fixture
def client() -> TestClient:
    return TestClient(webapp.app)


def test_deactivated_user_loses_access_on_next_request(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    is_active = {"value": True}

    async def _fake_get_session(token: str) -> Session | None:
        return _SESSION if token == "tok-user" else None

    async def _fake_get_user_by_id(user_id: str) -> User | None:
        if user_id != "user-1":
            return None
        return User(
            id="user-1",
            username="bob",
            password_hash="h",
            role="user",
            is_active=is_active["value"],
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
        )

    monkeypatch.setattr(session_resolver, "get_session", _fake_get_session)
    monkeypatch.setattr(session_resolver, "get_user_by_id", _fake_get_user_by_id)
    client.cookies.set("session", "tok-user")

    before = client.get("/api/images")
    assert before.status_code == 200

    # Simula o efeito de `PATCH /admin/users/{id}` com `is_active=False` —
    # nenhuma sessão é revogada, só a linha do usuário muda.
    is_active["value"] = False

    after = client.get("/api/images")
    assert after.status_code == 401
    assert after.json() == {"detail": "Unauthorized"}
