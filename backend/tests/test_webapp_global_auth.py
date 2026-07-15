"""Teste de integração: `require_auth` como dependency GLOBAL de `webapp.app`.

Cobre REQ-003 de `backend-api-routes-delta` (change
`autenticacao-jwt-rotas-protegidas`, task-rest-3): toda rota exige sessão por
padrão, exceto `PUBLIC_PATHS`; `images_router`/`documents_router` — antes
públicos — agora exigem `require_auth` sem precisar de nenhuma configuração
extra por rota (a proteção é herdada da `dependencies=[Depends(require_auth)]`
em `webapp.py`).

Diferente de `test_images_router.py`/`test_documents_router.py` (que fazem
`dependency_overrides` para testar o comportamento de negócio de cada
router), este arquivo testa a PRÓPRIA dependency global — por isso NÃO faz
override, apenas monkeypatcha `get_session`/`get_user_by_id` em
`session_resolver` (o núcleo compartilhado por trás de `require_auth`; as
únicas chamadas que tocariam Postgres) para simular sessão válida/ausente.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import src.infrastructure.web.auth_router as auth_router
import src.infrastructure.web.webapp as webapp
from src.infrastructure.auth import session_resolver
from src.infrastructure.auth.sessions import Session
from src.infrastructure.auth.users import User

_ADMIN_SESSION = Session(token="tok-admin", user_id="user-1", expires_at=None)  # type: ignore[arg-type]
_ADMIN_USER = User(id="user-1", username="alice", password_hash="h", role="admin", is_active=True)


@pytest.fixture
def client() -> TestClient:
    return TestClient(webapp.app)


def _allow_valid_session(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_get_session(token: str) -> Session | None:
        return _ADMIN_SESSION if token == "tok-admin" else None

    async def _fake_get_user_by_id(user_id: str) -> User | None:
        return _ADMIN_USER if user_id == "user-1" else None

    monkeypatch.setattr(session_resolver, "get_session", _fake_get_session)
    monkeypatch.setattr(session_resolver, "get_user_by_id", _fake_get_user_by_id)


# --- Protegido por padrão ----------------------------------------------------


def test_images_route_requires_auth_by_default(client: TestClient) -> None:
    """`GET /api/images` (antes público) agora exige sessão — sem cookie, 401."""
    response = client.get("/api/images")

    assert response.status_code == 401
    assert response.json() == {"detail": "Unauthorized"}


def test_documents_route_requires_auth_by_default(client: TestClient) -> None:
    """`GET /api/files/...` (antes público) agora exige sessão — sem cookie, 401."""
    response = client.get("/api/files/docx/anything.docx")

    assert response.status_code == 401
    assert response.json() == {"detail": "Unauthorized"}


def test_images_route_accepts_valid_session_cookie(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    _allow_valid_session(monkeypatch)
    client.cookies.set("session", "tok-admin")

    response = client.get("/api/images")

    assert response.status_code == 200


def test_unknown_session_token_is_rejected(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    _allow_valid_session(monkeypatch)
    client.cookies.set("session", "not-a-real-token")

    response = client.get("/api/images")

    assert response.status_code == 401


# --- PUBLIC_PATHS continua liberado ------------------------------------------


def test_public_login_route_does_not_require_session(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    """`/public/*` é isento pela própria dependency global `require_auth`.

    Sem cookie nenhum no client, um login com credenciais VÁLIDAS (mockadas)
    chega a criar sessão e retornar 200 com `Set-Cookie`. Isso só é possível
    se `require_auth` não bloqueou a requisição antes do handler — provando,
    sem ambiguidade, que o path público foi de fato liberado pela dependency
    global (um 401 teria a mesma forma vindo de qualquer um dos dois pontos,
    então só o caminho feliz distingue os dois).
    """
    active_user = User(id="user-9", username="alice", password_hash="h", role="user", is_active=True)

    async def _fake_get_user_by_username(username: str) -> User | None:
        return active_user

    async def _fake_create_session(user_id: str) -> str:
        return "new-tok"

    monkeypatch.setattr(auth_router, "get_user_by_username", _fake_get_user_by_username)
    monkeypatch.setattr(auth_router, "verify_password", lambda plain, hashed: True)
    monkeypatch.setattr(auth_router, "create_session", _fake_create_session)

    response = client.post("/public/login", json={"username": "alice", "password": "s3cr3t"})

    assert response.status_code == 200
    assert response.cookies.get("session") == "new-tok"
