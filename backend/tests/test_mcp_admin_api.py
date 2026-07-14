"""Testes de `mcp_admin_api` (task `unified-agent-realignment-task-mcp-3`).

Este roteador vive no `image_server.py` — um processo HTTP separado do
grafo do agente. Os testes montam o router isoladamente (sem subir o
`image_server` inteiro) e apontam as dependências (`mcp_config_store`,
overrides) para arquivos em `tmp_path`, para nunca tocar o
`backend/mcp_servers.json` real.

Cobre REQ-001 (CRUD via API), REQ-004 (status ao vivo, degradação
graciosa) e a classificação manual de capacidade (Q3 do design).
"""
from __future__ import annotations

import functools
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.agents.unified import mcp_admin_api, mcp_config_store

_FIXTURE_SERVER = Path(__file__).parent / "fixtures" / "mcp_test_server.py"


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """App isolado com o router montado, apontando o CRUD e os overrides
    para arquivos temporários — nunca o `mcp_servers.json` real."""
    servers_path = tmp_path / "mcp_servers.json"
    overrides_path = tmp_path / "mcp_tool_overrides.json"

    for name in ("list_servers", "add_server", "update_server", "delete_server"):
        monkeypatch.setattr(
            mcp_config_store, name, functools.partial(getattr(mcp_config_store, name), path=servers_path)
        )
    # `get_server` delegates to `list_servers(path)` internally — patching it
    # the same way as above would forward a second positional `path` on top
    # of the partial's already-bound kwarg. Rebind it to call the (already
    # patched, now argument-less) `list_servers` instead.
    monkeypatch.setattr(
        mcp_config_store, "get_server", lambda name: mcp_config_store.list_servers().get(name)
    )
    monkeypatch.setattr(
        mcp_admin_api, "load_overrides", functools.partial(mcp_admin_api.load_overrides, path=overrides_path)
    )
    monkeypatch.setattr(
        mcp_admin_api,
        "set_override",
        functools.partial(mcp_admin_api.set_override, path=overrides_path),
    )
    monkeypatch.setattr(
        mcp_admin_api,
        "remove_override",
        functools.partial(mcp_admin_api.remove_override, path=overrides_path),
    )

    app = FastAPI()
    app.include_router(mcp_admin_api.router)
    return TestClient(app)


# =========================================================================== #
# Servidores — CRUD (REQ-001)
# =========================================================================== #
def test_get_servers_empty_when_none_configured(client: TestClient) -> None:
    res = client.get("/api/mcp/servers")
    assert res.status_code == 200
    assert res.json() == {"servers": []}


def test_create_server_never_echoes_secret_value(client: TestClient) -> None:
    """REQ-007: a resposta de criação devolve o NOME da env var, nunca um valor."""
    res = client.post(
        "/api/mcp/servers",
        json={
            "name": "meu-servidor",
            "command": "npx",
            "args": ["-y", "@some/server"],
            "env": {"API_KEY": "MEU_SERVIDOR_API_KEY"},
        },
    )
    assert res.status_code == 201
    body = res.json()
    # A resposta carrega o NOME da env var (uma referência), nunca teria
    # como carregar um "valor resolvido" — a API nunca chama os.environ.
    assert body["env"] == {"API_KEY": "MEU_SERVIDOR_API_KEY"}


def test_create_server_rejects_duplicate(client: TestClient) -> None:
    payload = {"name": "dup", "command": "cmd", "args": [], "env": {}}
    assert client.post("/api/mcp/servers", json=payload).status_code == 201
    res = client.post("/api/mcp/servers", json=payload)
    assert res.status_code == 400
    assert "já existe" in res.json()["detail"]


def test_update_server_changes_args(client: TestClient) -> None:
    client.post(
        "/api/mcp/servers",
        json={"name": "srv", "command": "npx", "args": ["-y", "a"], "env": {}},
    )
    res = client.put(
        "/api/mcp/servers/srv",
        json={"command": "npx", "args": ["-y", "b"], "env": {}},
    )
    assert res.status_code == 200
    assert res.json()["args"] == ["-y", "b"]


def test_update_nonexistent_server_returns_400(client: TestClient) -> None:
    res = client.put("/api/mcp/servers/ghost", json={"command": "cmd", "args": [], "env": {}})
    assert res.status_code == 400


def test_delete_server_removes_it(client: TestClient) -> None:
    client.post("/api/mcp/servers", json={"name": "srv", "command": "cmd", "args": [], "env": {}})
    res = client.delete("/api/mcp/servers/srv")
    assert res.status_code == 204
    assert client.get("/api/mcp/servers").json() == {"servers": []}


# =========================================================================== #
# Status ao vivo (REQ-004)
# =========================================================================== #
def test_get_servers_reports_connected_status_for_real_server(client: TestClient) -> None:
    client.post(
        "/api/mcp/servers",
        json={
            "name": "jeff-ai-test-server",
            "command": sys.executable,
            "args": [str(_FIXTURE_SERVER)],
            "env": {},
        },
    )
    res = client.get("/api/mcp/servers")
    assert res.status_code == 200
    servers = res.json()["servers"]
    assert len(servers) == 1
    assert servers[0]["status"] == "connected"
    assert servers[0]["tool_count"] == 2


def test_get_servers_reports_error_status_without_crashing(client: TestClient) -> None:
    """REQ-004: um servidor com comando inexistente vira status=error —
    não derruba a listagem inteira nem a request."""
    client.post(
        "/api/mcp/servers",
        json={
            "name": "broken",
            "command": "/definitely/not/a/real/executable-xyz",
            "args": [],
            "env": {},
        },
    )
    res = client.get("/api/mcp/servers")
    assert res.status_code == 200
    servers = res.json()["servers"]
    assert servers[0]["status"] == "error"
    assert servers[0]["message"]


def test_get_server_tools_lists_name_description_and_capability(client: TestClient) -> None:
    client.post(
        "/api/mcp/servers",
        json={
            "name": "jeff-ai-test-server",
            "command": sys.executable,
            "args": [str(_FIXTURE_SERVER)],
            "env": {},
        },
    )
    res = client.get("/api/mcp/servers/jeff-ai-test-server/tools")
    assert res.status_code == 200
    tools = res.json()["tools"]
    names = {t["name"] for t in tools}
    assert names == {"echo", "add"}
    for tool in tools:
        assert tool["qualified_name"] == f"mcp__jeff_ai_test_server__{tool['name']}"
        # Não classificada manualmente ainda -> fail-safe.
        assert tool["capability"] == "unknown"


def test_get_tools_for_unknown_server_returns_404(client: TestClient) -> None:
    res = client.get("/api/mcp/servers/ghost/tools")
    assert res.status_code == 404


# =========================================================================== #
# Classificação manual de capacidade (Q3 do design)
# =========================================================================== #
def test_capabilities_endpoint_lists_valid_values(client: TestClient) -> None:
    res = client.get("/api/mcp/capabilities")
    assert res.status_code == 200
    assert "read" in res.json()["capabilities"]
    assert "unknown" in res.json()["capabilities"]


def test_set_and_clear_capability_override(client: TestClient) -> None:
    tool_name = "mcp__srv__read_status"
    res = client.post(
        "/api/mcp/tools/capability", json={"tool_name": tool_name, "capability": "read"}
    )
    assert res.status_code == 200
    assert res.json()["overrides"][tool_name] == "read"

    res = client.get("/api/mcp/tools/overrides")
    assert res.json()["overrides"][tool_name] == "read"

    res = client.delete(f"/api/mcp/tools/capability/{tool_name}")
    assert res.status_code == 200
    assert tool_name not in res.json()["overrides"]


def test_set_capability_rejects_non_mcp_tool(client: TestClient) -> None:
    res = client.post(
        "/api/mcp/tools/capability", json={"tool_name": "edit_file", "capability": "read"}
    )
    assert res.status_code == 400


def test_set_capability_rejects_invalid_capability_value(client: TestClient) -> None:
    res = client.post(
        "/api/mcp/tools/capability",
        json={"tool_name": "mcp__srv__tool", "capability": "not-real"},
    )
    assert res.status_code == 400
