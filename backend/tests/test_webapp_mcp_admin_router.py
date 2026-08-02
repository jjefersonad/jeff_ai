"""Teste de integração: `mcp_admin_router` montado em `webapp.py` (task
`retire-image-server-task-core-1`).

Cobre custom-http-app REQ-004 (cenário 1) e mcp-client REQ-008 (cenários 1
e 2): `/api/mcp/*` responde do mesmo processo/app FastAPI que `/api/images`
e o resto de `webapp.py` — não mais de um processo `image_server.py`
separado.

Monkeypatcha `mcp_config_store.list_servers` para um `tmp_path` (mesmo
padrão de `test_mcp_admin_api.py`) para nunca tocar o
`backend/mcp_servers.json` real.
"""
from __future__ import annotations

import functools
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import src.infrastructure.web.webapp as webapp
from src.agents.unified import mcp_config_store
from src.infrastructure.auth.dependencies import require_auth
from src.infrastructure.auth.users import User

_USER = User(id="user-1", username="alice", password_hash="h", role="user", is_active=True)


@pytest.fixture
def client() -> TestClient:
    return TestClient(webapp.app)


def test_mcp_servers_route_requires_auth_by_default(client: TestClient) -> None:
    """`GET /api/mcp/servers` sem cookie de sessão retorna 401 (global `require_auth`)."""
    response = client.get("/api/mcp/servers")

    assert response.status_code == 401
    assert response.json() == {"detail": "Unauthorized"}


def test_mcp_servers_route_reachable_with_valid_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    """Com `require_auth` satisfeito, a requisição chega ao handler de
    `mcp_admin_api` e retorna 200 — provando que `/api/mcp/*` roda no mesmo
    app/processo que o resto de `webapp.py`, não em `image_server.py`."""
    servers_path = tmp_path / "mcp_servers.json"
    monkeypatch.setattr(
        mcp_config_store,
        "list_servers",
        functools.partial(mcp_config_store.list_servers, path=servers_path),
    )
    webapp.app.dependency_overrides[require_auth] = lambda: _USER
    try:
        response = client.get("/api/mcp/servers")
    finally:
        webapp.app.dependency_overrides.pop(require_auth, None)

    assert response.status_code == 200
    assert response.json() == {"servers": []}
