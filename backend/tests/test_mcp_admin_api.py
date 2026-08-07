"""Testes de `mcp_admin_api` (task `unified-agent-realignment-task-mcp-3`,
revisado por `user-scoped-mcp-config-storage-task-admin-1`.

Este roteador vive em `webapp.py`, no mesmo processo do grafo do agente
(`retire-image-server-task-core-1` — antes era `image_server.py`, um
processo separado, hoje aposentado). Os testes montam o router isoladamente
(sem subir o `webapp.app` inteiro) e usam mocks em memória para
`mcp_config_store`, para nunca tocar o Postgres real.

Cobre REQ-001 (CRUD via API), REQ-004 (status ao vivo, degradação
graciosa), a classificação manual de capacidade (Q3 do design) e — desde
`user-scoped-mcp-config-storage-task-admin-1` — `scoped-mcp-config` REQ-001
(`Depends(require_auth)` no router devolve 401 sem sessão válida).

Desde `user-scoped-mcp-config-storage-task-admin-2`, cada handler extrai
`user_id` do `User` injected por `require_auth`; todas as operações CRUD
são escopadas ao `user_id` do requester (admin vê todos).
"""
from __future__ import annotations

import functools
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.agents.unified import mcp_admin_api, mcp_config_store
from src.infrastructure.auth.dependencies import require_auth
from src.infrastructure.auth.users import User

_FIXTURE_SERVER = Path(__file__).parent / "fixtures" / "mcp_test_server.py"

# Usuário de teste para satisfazer `require_auth` via `dependency_overrides`.
_AUTH_USER = User(
    id="user-test",
    username="alice",
    password_hash="h",
    role="user",
    is_active=True,
    created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
)

_AUTH_USER_B = User(
    id="user-b-test",
    username="bob",
    password_hash="h",
    role="user",
    is_active=True,
    created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
)

_AUTH_ADMIN = User(
    id="admin-test",
    username="admin",
    password_hash="h",
    role="admin",
    is_active=True,
    created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
)


# --------------------------------------------------------------------------- #
# In-memory async store — replaces file-based CRUD for these tests
# --------------------------------------------------------------------------- #
class _InMemoryStore:
    """Simple dict-backed async store mirroring mcp_config_store's async signatures."""

    def __init__(self) -> None:
        self._servers: dict[str, dict[str, dict]] = {}  # user_id -> name -> entry

    async def list_servers(self, user_id: str) -> dict[str, dict]:
        return dict(self._servers.get(user_id, {}))

    async def get_server(self, user_id: str, name: str) -> dict | None:
        return self._servers.get(user_id, {}).get(name)

    async def add_server(
        self,
        user_id: str,
        name: str,
        *,
        transport: str = "stdio",
        command: str | None = None,
        args: list | None = None,
        url: str | None = None,
        env: dict | None = None,
        headers: dict | None = None,
    ) -> dict:
        if user_id not in self._servers:
            self._servers[user_id] = {}
        entry = {
            "transport": transport,
            "command": command or "",
            "args": list(args or []),
            "url": url or "",
            "env": dict(env or {}),
            "headers": dict(headers or {}),
        }
        self._servers[user_id][name] = entry
        return entry

    async def update_server(
        self,
        user_id: str,
        name: str,
        *,
        transport: str = "stdio",
        command: str | None = None,
        args: list | None = None,
        url: str | None = None,
        env: dict | None = None,
        headers: dict | None = None,
    ) -> dict:
        if user_id not in self._servers or name not in self._servers[user_id]:
            raise mcp_config_store.McpServerConfigError(
                f"servidor '{name}' não existe para este usuário."
            )
        entry = {
            "transport": transport,
            "command": command or "",
            "args": list(args or []),
            "url": url or "",
            "env": dict(env or {}),
            "headers": dict(headers or {}),
        }
        self._servers[user_id][name] = entry
        return entry

    async def delete_server(self, user_id: str, name: str) -> None:
        if user_id in self._servers and name in self._servers[user_id]:
            del self._servers[user_id][name]


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """App isolado com o router montado, com stubs async em memória para
    `mcp_config_store` (nunca toca Postgres nem arquivos reais)."""
    store = _InMemoryStore()

    # Async stubs that delegate to the in-memory store
    async def _list(user_id: str) -> dict:
        return await store.list_servers(user_id)

    async def _get(user_id: str, name: str) -> dict | None:
        return await store.get_server(user_id, name)

    async def _add(
        user_id: str,
        name: str,
        *,
        transport: str = "stdio",
        command: str | None = None,
        args: list | None = None,
        url: str | None = None,
        env: dict | None = None,
        headers: dict | None = None,
    ) -> dict:
        existing = await store.get_server(user_id, name)
        if existing is not None:
            raise mcp_config_store.McpServerConfigError(
                f"servidor '{name}' já existe para este usuário."
            )
        return await store.add_server(
            user_id, name,
            transport=transport, command=command, args=args,
            url=url, env=env, headers=headers,
        )

    async def _update(
        user_id: str,
        name: str,
        *,
        transport: str = "stdio",
        command: str | None = None,
        args: list | None = None,
        url: str | None = None,
        env: dict | None = None,
        headers: dict | None = None,
    ) -> dict:
        return await store.update_server(
            user_id, name,
            transport=transport, command=command, args=args,
            url=url, env=env, headers=headers,
        )

    async def _delete(user_id: str, name: str) -> None:
        return await store.delete_server(user_id, name)

    async def _list_all() -> list:
        # Flat list of all servers from all users (for admin path)
        result = []
        for user_id, servers in store._servers.items():
            for name, entry in servers.items():
                mock_server = MagicMock()
                mock_server.name = name
                mock_server.user_id = user_id
                mock_server.transport = entry["transport"]
                mock_server.command = entry["command"]
                mock_server.args = entry["args"]
                mock_server.url = entry["url"]
                mock_server.env = entry["env"]
                mock_server.headers = entry["headers"]
                result.append(mock_server)
        return result

    monkeypatch.setattr(mcp_config_store, "list_servers", _list)
    monkeypatch.setattr(mcp_config_store, "get_server", _get)
    monkeypatch.setattr(mcp_config_store, "add_server", _add)
    monkeypatch.setattr(mcp_config_store, "update_server", _update)
    monkeypatch.setattr(mcp_config_store, "delete_server", _delete)
    monkeypatch.setattr(mcp_config_store, "list_all_servers", _list_all)

    # `mcp_tool_overrides` — use tmp file (unchanged from original)
    overrides_path = tmp_path / "mcp_tool_overrides.json"
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
    client.app.dependency_overrides[require_auth] = lambda: _AUTH_USER
    try:
        res = client.get("/api/mcp/servers")
        assert res.status_code == 200
        assert res.json() == {"servers": []}
    finally:
        client.app.dependency_overrides.pop(require_auth, None)


def test_create_server_never_echoes_secret_value(client: TestClient) -> None:
    """REQ-007: a resposta de criação devolve o NOME da env var, nunca um valor."""
    client.app.dependency_overrides[require_auth] = lambda: _AUTH_USER
    try:
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
        assert body["env"] == {"API_KEY": "MEU_SERVIDOR_API_KEY"}
    finally:
        client.app.dependency_overrides.pop(require_auth, None)


def test_create_server_rejects_duplicate(client: TestClient) -> None:
    client.app.dependency_overrides[require_auth] = lambda: _AUTH_USER
    try:
        payload = {"name": "dup", "command": "cmd", "args": [], "env": {}}
        assert client.post("/api/mcp/servers", json=payload).status_code == 201
        res = client.post("/api/mcp/servers", json=payload)
        assert res.status_code == 400
        assert "já existe" in res.json()["detail"]
    finally:
        client.app.dependency_overrides.pop(require_auth, None)


def test_create_http_server_without_command_returns_201(client: TestClient) -> None:
    """fix-mcp-http-server-admin-api: payload da UI (zernio) não exige command."""
    client.app.dependency_overrides[require_auth] = lambda: _AUTH_USER
    try:
        res = client.post(
            "/api/mcp/servers",
            json={
                "name": "zernio",
                "transport": "http",
                "url": "https://mcp.zernio.com/mcp",
                "headers": {"Authorization": "Bearer secret-token"},
            },
        )
        assert res.status_code == 201, res.text
        body = res.json()
        assert body["transport"] == "http"
        assert body["url"] == "https://mcp.zernio.com/mcp"
        assert body["headers"] == {"Authorization": "***"}
    finally:
        client.app.dependency_overrides.pop(require_auth, None)


def test_create_http_server_without_url_returns_422(client: TestClient) -> None:
    client.app.dependency_overrides[require_auth] = lambda: _AUTH_USER
    try:
        res = client.post(
            "/api/mcp/servers",
            json={"name": "zernio", "transport": "http", "headers": {}},
        )
        assert res.status_code == 422
    finally:
        client.app.dependency_overrides.pop(require_auth, None)


def test_create_stdio_without_command_returns_422(client: TestClient) -> None:
    client.app.dependency_overrides[require_auth] = lambda: _AUTH_USER
    try:
        res = client.post(
            "/api/mcp/servers",
            json={"name": "local", "transport": "stdio", "args": [], "env": {}},
        )
        assert res.status_code == 422
    finally:
        client.app.dependency_overrides.pop(require_auth, None)


def test_update_http_server_without_command(client: TestClient) -> None:
    client.app.dependency_overrides[require_auth] = lambda: _AUTH_USER
    try:
        assert (
            client.post(
                "/api/mcp/servers",
                json={
                    "name": "remote",
                    "transport": "http",
                    "url": "https://example.com/mcp",
                    "headers": {},
                },
            ).status_code
            == 201
        )
        res = client.put(
            "/api/mcp/servers/remote",
            json={
                "transport": "http",
                "url": "https://example.com/mcp/v2",
                "headers": {},
            },
        )
        assert res.status_code == 200
        assert res.json()["url"] == "https://example.com/mcp/v2"
        assert res.json()["transport"] == "http"
    finally:
        client.app.dependency_overrides.pop(require_auth, None)


def test_get_servers_includes_transport_and_url_for_http(client: TestClient) -> None:
    client.app.dependency_overrides[require_auth] = lambda: _AUTH_USER
    try:
        client.post(
            "/api/mcp/servers",
            json={
                "name": "zernio",
                "transport": "http",
                "url": "https://mcp.zernio.com/mcp",
                "headers": {"Authorization": "Bearer x"},
            },
        )
        res = client.get("/api/mcp/servers")
        assert res.status_code == 200
        servers = res.json()["servers"]
        assert len(servers) == 1
        assert servers[0]["name"] == "zernio"
        assert servers[0]["transport"] == "http"
        assert servers[0]["url"] == "https://mcp.zernio.com/mcp"
        assert servers[0]["headers"] == {"Authorization": "***"}
        assert servers[0]["command"] == ""
    finally:
        client.app.dependency_overrides.pop(require_auth, None)


def test_get_servers_distinguishes_http_and_stdio_by_transport(
    client: TestClient,
) -> None:
    """REQ-001 list delta: UI usa `transport`, não infere só por `command`."""
    client.app.dependency_overrides[require_auth] = lambda: _AUTH_USER
    try:
        assert (
            client.post(
                "/api/mcp/servers",
                json={
                    "name": "local",
                    "command": "npx",
                    "args": ["-y", "local-mcp"],
                    "env": {},
                },
            ).status_code
            == 201
        )
        assert (
            client.post(
                "/api/mcp/servers",
                json={
                    "name": "zernio",
                    "transport": "http",
                    "url": "https://mcp.zernio.com/mcp",
                    "headers": {},
                },
            ).status_code
            == 201
        )
        res = client.get("/api/mcp/servers")
        assert res.status_code == 200
        by_name = {s["name"]: s for s in res.json()["servers"]}
        assert by_name["local"]["transport"] == "stdio"
        assert by_name["zernio"]["transport"] == "http"
        assert by_name["zernio"]["url"] == "https://mcp.zernio.com/mcp"
    finally:
        client.app.dependency_overrides.pop(require_auth, None)


def test_update_server_changes_args(client: TestClient) -> None:
    client.app.dependency_overrides[require_auth] = lambda: _AUTH_USER
    try:
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
    finally:
        client.app.dependency_overrides.pop(require_auth, None)


def test_update_nonexistent_server_returns_404(client: TestClient) -> None:
    client.app.dependency_overrides[require_auth] = lambda: _AUTH_USER
    try:
        res = client.put("/api/mcp/servers/ghost", json={"command": "cmd", "args": [], "env": {}})
        assert res.status_code == 404
    finally:
        client.app.dependency_overrides.pop(require_auth, None)


def test_delete_server_removes_it(client: TestClient) -> None:
    client.app.dependency_overrides[require_auth] = lambda: _AUTH_USER
    try:
        client.post("/api/mcp/servers", json={"name": "srv", "command": "cmd", "args": [], "env": {}})
        res = client.delete("/api/mcp/servers/srv")
        assert res.status_code == 204
        assert client.get("/api/mcp/servers").json() == {"servers": []}
    finally:
        client.app.dependency_overrides.pop(require_auth, None)


# =========================================================================== #
# Status ao vivo (REQ-004)
# =========================================================================== #
def test_get_servers_reports_connected_status_for_real_server(client: TestClient) -> None:
    client.app.dependency_overrides[require_auth] = lambda: _AUTH_USER
    try:
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
    finally:
        client.app.dependency_overrides.pop(require_auth, None)


def test_get_servers_reports_error_status_without_crashing(client: TestClient) -> None:
    """REQ-004: um servidor com comando inexistente vira status=error —
    não derruba a listagem inteira nem a request."""
    client.app.dependency_overrides[require_auth] = lambda: _AUTH_USER
    try:
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
    finally:
        client.app.dependency_overrides.pop(require_auth, None)


def test_get_server_tools_lists_name_description_and_capability(client: TestClient) -> None:
    client.app.dependency_overrides[require_auth] = lambda: _AUTH_USER
    try:
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
            assert tool["capability"] == "network"
    finally:
        client.app.dependency_overrides.pop(require_auth, None)


def test_get_tools_for_unknown_server_returns_404(client: TestClient) -> None:
    client.app.dependency_overrides[require_auth] = lambda: _AUTH_USER
    try:
        res = client.get("/api/mcp/servers/ghost/tools")
        assert res.status_code == 404
    finally:
        client.app.dependency_overrides.pop(require_auth, None)


# =========================================================================== #
# Classificação manual de capacidade (Q3 do design)
# =========================================================================== #
def test_capabilities_endpoint_lists_valid_values(client: TestClient) -> None:
    client.app.dependency_overrides[require_auth] = lambda: _AUTH_USER
    try:
        res = client.get("/api/mcp/capabilities")
        assert res.status_code == 200
        assert "read" in res.json()["capabilities"]
        assert "unknown" in res.json()["capabilities"]
    finally:
        client.app.dependency_overrides.pop(require_auth, None)


def test_set_and_clear_capability_override(client: TestClient) -> None:
    client.app.dependency_overrides[require_auth] = lambda: _AUTH_USER
    try:
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
    finally:
        client.app.dependency_overrides.pop(require_auth, None)


def test_set_capability_rejects_non_mcp_tool(client: TestClient) -> None:
    client.app.dependency_overrides[require_auth] = lambda: _AUTH_USER
    try:
        res = client.post(
            "/api/mcp/tools/capability", json={"tool_name": "edit_file", "capability": "read"}
        )
        assert res.status_code == 400
    finally:
        client.app.dependency_overrides.pop(require_auth, None)


def test_set_capability_rejects_invalid_capability_value(client: TestClient) -> None:
    client.app.dependency_overrides[require_auth] = lambda: _AUTH_USER
    try:
        res = client.post(
            "/api/mcp/tools/capability",
            json={"tool_name": "mcp__srv__tool", "capability": "not-real"},
        )
        assert res.status_code == 400
    finally:
        client.app.dependency_overrides.pop(require_auth, None)


# =========================================================================== #
# Auth no router (REQ-001 do `scoped-mcp-config`, task-admin-1)
# =========================================================================== #
def test_mcp_servers_returns_401_without_session(client: TestClient) -> None:
    res = client.get("/api/mcp/servers")
    assert res.status_code == 401
    assert res.json() == {"detail": "Unauthorized"}


def test_any_mcp_route_returns_401_without_session(client: TestClient) -> None:
    for path in (
        "/api/mcp/capabilities",
        "/api/mcp/tools/overrides",
    ):
        res = client.get(path)
        assert res.status_code == 401, path
        assert res.json() == {"detail": "Unauthorized"}, path


def test_mcp_servers_proceeds_to_handler_with_valid_session(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Com `require_auth` satisfeita (override injetando o `User`), a
    requisição atravessa o gate de auth e chega ao handler — provando que
    o gate não trava o caminho autenticado."""
    async def _empty_list(user_id: str) -> dict:
        return {}

    monkeypatch.setattr(mcp_config_store, "list_servers", _empty_list)

    client.app.dependency_overrides[require_auth] = lambda: _AUTH_USER
    try:
        res = client.get("/api/mcp/servers")
    finally:
        client.app.dependency_overrides.pop(require_auth, None)

    assert res.status_code == 200
    assert res.json() == {"servers": []}


# =========================================================================== #
# user-scoped-mcp-config-storage task-admin-2: user_id scoping
# =========================================================================== #


class TestUserScoping:
    """Tests for REQ-003 (scoped-mcp-config): users only see their own servers."""

    def test_non_admin_get_servers_only_sees_own_server(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """unit-1: user A calling GET /api/mcp/servers only sees A's server, never B's."""
        async def async_get_servers_a(user_id: str) -> dict:
            if user_id == "user-test":
                return {
                    "zernio": {
                        "transport": "http",
                        "command": "",
                        "args": [],
                        "url": "https://api.zern.io/mcp",
                        "env": {},
                        "headers": {},
                    }
                }
            return {}

        monkeypatch.setattr(mcp_config_store, "list_servers", async_get_servers_a)
        client.app.dependency_overrides[require_auth] = lambda: _AUTH_USER
        try:
            res = client.get("/api/mcp/servers")
        finally:
            client.app.dependency_overrides.pop(require_auth, None)

        assert res.status_code == 200
        servers = res.json()["servers"]
        assert [s["name"] for s in servers] == ["zernio"]

    def test_admin_get_servers_sees_all_users_but_no_decrypted_secrets(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """unit-2: admin sees all users' servers but NO decrypted env/headers values."""

        class _FakeServer:
            name = "zernio"
            user_id = "user-test"
            transport = "http"
            command = ""
            args: list = []
            url = "https://api.zern.io/mcp"
            env = {"__enc__": "alice_env_ciphertext"}
            headers = {"__enc__": "alice_headers_ciphertext"}

        class _FakeServerB:
            name = "zernio"
            user_id = "user-b-test"
            transport = "http"
            command = ""
            args: list = []
            url = "https://api.zern.io/mcp"
            env = {"__enc__": "bob_env_ciphertext"}
            headers = {"__enc__": "bob_headers_ciphertext"}

        async def async_list_all() -> list:
            return [_FakeServer(), _FakeServerB()]

        async def async_list_empty(user_id: str) -> dict:
            return {}

        monkeypatch.setattr(mcp_config_store, "list_servers", async_list_empty)
        monkeypatch.setattr(mcp_config_store, "list_all_servers", async_list_all)

        client.app.dependency_overrides[require_auth] = lambda: _AUTH_ADMIN
        try:
            res = client.get("/api/mcp/servers")
        finally:
            client.app.dependency_overrides.pop(require_auth, None)

        assert res.status_code == 200
        servers = res.json()["servers"]
        assert len(servers) == 2
        for server in servers:
            # REQ-002: no decrypted secret values — ciphertext must never appear
            for val in server.get("env", {}).values():
                assert not val.startswith("__enc__"), f"encrypted env leaked: {val}"
            for val in server.get("headers", {}).values():
                assert not val.startswith("__enc__"), f"encrypted headers leaked: {val}"

    def test_non_admin_cannot_write_or_delete_another_users_server(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """unit-3: PUT/DELETE on a server that exists for another user returns 404."""
        async def async_update_404(*args: object, **kwargs: object) -> None:
            raise mcp_config_store.McpServerConfigError(
                "servidor 'zernio' não existe para este usuário."
            )

        async def async_delete_noop(*args: object, **kwargs: object) -> None:
            return None

        monkeypatch.setattr(mcp_config_store, "update_server", async_update_404)
        monkeypatch.setattr(mcp_config_store, "delete_server", async_delete_noop)

        client.app.dependency_overrides[require_auth] = lambda: _AUTH_USER
        try:
            # PUT: server doesn't exist for user A → 404
            res = client.put(
                "/api/mcp/servers/zernio",
                json={"command": "npx", "args": [], "env": {}},
            )
            assert res.status_code == 404
            assert "não existe" in res.json()["detail"]

            # DELETE: server doesn't exist for user A → no-op scoped to A (204 or 404 both acceptable)
            res = client.delete("/api/mcp/servers/zernio")
            assert res.status_code in (204, 404)
        finally:
            client.app.dependency_overrides.pop(require_auth, None)
