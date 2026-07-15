"""Testes de `src/infrastructure/web/auth.py` (handler nativo do LangGraph).

Cobre REQ-001/REQ-002/REQ-003 de `langgraph-native-auth-middleware` (change
`autenticacao-jwt-rotas-protegidas`, task-langgraph-auth-1):
- Sessão válida autentica e resolve o mesmo `User` usado por `require_auth`.
- Sessão ausente/desconhecida/expirada é rejeitada com
  `Auth.exceptions.HTTPException(401)` — ANTES de qualquer execução do grafo,
  já que a rejeição acontece na própria função de autenticação.
- `/public/*` é liberado sem sessão (bypass explícito, testado sem sequer
  chamar `get_session`/`get_user_by_id`, provando que o Postgres não é
  tocado nesse caminho).
- REQ-002 (cobertura uniforme dos 4 graph IDs): validado estaticamente —
  `langgraph.json` registra um único `auth.path` para o processo inteiro,
  então os 4 graph IDs (que compilam o mesmo grafo `unified`) são cobertos
  pelo mesmo handler por construção, não por configuração por-grafo.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from langgraph_sdk import Auth
from starlette.requests import Request

from src.infrastructure.auth import session_resolver
from src.infrastructure.auth.sessions import Session
from src.infrastructure.auth.users import User
from src.infrastructure.web.auth import authenticate

_VALID_SESSION = Session(token="tok", user_id="user-1", expires_at=None)  # type: ignore[arg-type]
_ADMIN_USER = User(id="user-1", username="alice", password_hash="h", role="admin", is_active=True)


def _request(path: str, cookie: str | None = None) -> Request:
    headers = []
    if cookie is not None:
        headers.append((b"cookie", f"session={cookie}".encode()))
    scope = {"type": "http", "method": "GET", "path": path, "headers": headers, "query_string": b""}
    return Request(scope)


# --- REQ-001: sessão válida autentica ---------------------------------------


async def test_authenticate_resolves_user_from_valid_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PUBLIC_PATHS", raising=False)

    async def _fake_get_session(token: str) -> Session | None:
        return _VALID_SESSION

    async def _fake_get_user_by_id(user_id: str) -> User | None:
        return _ADMIN_USER

    monkeypatch.setattr(session_resolver, "get_session", _fake_get_session)
    monkeypatch.setattr(session_resolver, "get_user_by_id", _fake_get_user_by_id)

    result = await authenticate(_request("/threads", cookie="tok"))

    assert result == {
        "identity": "user-1",
        "display_name": "alice",
        "permissions": ["admin"],
        "is_authenticated": True,
    }


# --- REQ-001 (cenário negativo): sem sessão válida → 401 antes do grafo -----


async def test_authenticate_rejects_missing_session_with_401(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PUBLIC_PATHS", raising=False)

    with pytest.raises(Auth.exceptions.HTTPException) as exc_info:
        await authenticate(_request("/threads"))

    assert exc_info.value.status_code == 401


async def test_authenticate_rejects_unknown_session_token_with_401(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PUBLIC_PATHS", raising=False)

    async def _fake_get_session(token: str) -> Session | None:
        return None

    monkeypatch.setattr(session_resolver, "get_session", _fake_get_session)

    with pytest.raises(Auth.exceptions.HTTPException) as exc_info:
        await authenticate(_request("/runs", cookie="unknown"))

    assert exc_info.value.status_code == 401


# --- Bypass explícito de /public/* ------------------------------------------


async def test_authenticate_bypasses_public_path_without_touching_postgres(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PUBLIC_PATHS", raising=False)

    async def _fail_if_called(*args: object, **kwargs: object) -> None:
        raise AssertionError("get_session não deveria ser chamado para path público")

    monkeypatch.setattr(session_resolver, "get_session", _fail_if_called)

    result = await authenticate(_request("/public/login"))

    assert result == {"identity": "public", "is_authenticated": False, "permissions": []}


# --- REQ-002: um único auth.path cobre os 4 graph IDs -----------------------


def test_langgraph_json_registers_single_auth_handler_for_all_graph_ids() -> None:
    config_path = Path(__file__).resolve().parent.parent / "langgraph.json"
    config = json.loads(config_path.read_text())

    assert config["auth"]["path"] == "./src/infrastructure/web/auth.py:auth"
    # Um único bloco `auth` no nível raiz cobre todos os graph IDs listados —
    # não há (e não deve haver) configuração de auth por-grafo.
    assert set(config["graphs"]) == {"unified", "agent", "sdd_agent", "assistant"}
