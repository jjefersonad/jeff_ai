"""Testes do cliente MCP básico (task `unified-agent-realignment-task-mcp-1`,
revisado pela task `user-scoped-mcp-config-storage-task-client-1`).

Cobre REQ-004, REQ-006, REQ-007, REQ-010 do `mcp-client` (via `build_connection`,
que continua com a mesma lógica de parsing/validação de entrada — só deixou de
ser alimentada por um arquivo JSON) e o REQ-009 revisado (`load_mcp_server_config`
agora resolve por `user_id`, delegando a `mcp_config_store`, não mais a
`backend/mcp_servers.json`). O teste de conexão real
(`test_list_mcp_tools_connects_to_real_local_server_and_lists_tools`) roda um
servidor MCP de verdade como subprocesso (`tests/fixtures/mcp_test_server.py`),
não um mock do transporte.

A seção C (`mcp-remote-http-transport`) espelha esse mesmo princípio pro
transporte `http`: `tests/fixtures/mcp_test_http_server.py` sobe um servidor
real via `uvicorn`, e os testes conectam via HTTP de verdade — não mockado.
"""
from __future__ import annotations

import contextlib
import os
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest

from src.agents.unified.mcp_client import (
    McpConfigError,
    McpServerConnectionError,
    build_connection,
    list_mcp_tools,
    load_mcp_server_config,
)
from src.agents.unified.mcp_config_store import add_server
from src.application.ports.mcp_server_repository import McpServerRepositoryPort
from src.domain.mcp import McpServerConfig

_FIXTURE_SERVER = Path(__file__).parent / "fixtures" / "mcp_test_server.py"
_HTTP_FIXTURE_SERVER = Path(__file__).parent / "fixtures" / "mcp_test_http_server.py"


class _FakeRepository(McpServerRepositoryPort):
    """Repositório em memória — mesma semântica de `PostgresMcpServerRepository`
    (chave `(user_id, name)`), sem tocar Postgres. Espelha `_FakeRepository` de
    `test_mcp_config_store.py`."""

    def __init__(self) -> None:
        self._rows: dict[tuple[str, str], McpServerConfig] = {}

    async def save(self, server: McpServerConfig) -> None:
        self._rows[(server.user_id, server.name)] = server

    async def get(self, user_id: str, name: str) -> McpServerConfig | None:
        return self._rows.get((user_id, name))

    async def list_by_user(self, user_id: str) -> list[McpServerConfig]:
        return [s for (uid, _name), s in self._rows.items() if uid == user_id]

    async def list_all(self) -> list[McpServerConfig]:
        return list(self._rows.values())

    async def delete(self, user_id: str, name: str) -> None:
        self._rows.pop((user_id, name), None)


@pytest.fixture
def repo() -> _FakeRepository:
    return _FakeRepository()


# =========================================================================== #
# A. build_connection — REQ-006, REQ-007 (transporte, campos obrigatórios,
#    resolução de ${VAR}). Extraído de `load_mcp_server_config` desde a task
#    `unified-agent-realignment-task-mcp-1` — testado direto, sem round-trip
#    por arquivo, já que é aqui que a lógica de fato mora.
# =========================================================================== #
def test_parses_stdio_entry() -> None:
    connection = build_connection("my-server", {"command": "npx", "args": ["-y", "@some/server"]})
    assert connection["transport"] == "stdio"
    assert connection["command"] == "npx"
    assert connection["args"] == ["-y", "@some/server"]


def test_resolves_env_var_reference(monkeypatch: pytest.MonkeyPatch) -> None:
    """REQ-007: `${VAR}` é substituído por `os.environ`, nunca hardcoded."""
    monkeypatch.setenv("JEFF_TEST_MCP_SECRET", "s3cr3t-value")
    connection = build_connection("srv", {"command": "some-cmd", "env": {"API_KEY": "${JEFF_TEST_MCP_SECRET}"}})
    assert connection["env"] == {"API_KEY": "s3cr3t-value"}  # type: ignore[typeddict-item]


def test_raises_when_referenced_env_var_is_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("JEFF_TEST_MCP_MISSING", raising=False)
    with pytest.raises(McpConfigError, match="JEFF_TEST_MCP_MISSING"):
        build_connection("srv", {"command": "some-cmd", "env": {"API_KEY": "${JEFF_TEST_MCP_MISSING}"}})


def test_unsupported_transport_is_rejected_explicitly() -> None:
    """REQ-006: transporte fora de escopo (`http` NÃO conta mais — ver
    `test_parses_http_entry_without_command`) é recusado com mensagem clara,
    não ignorado."""
    with pytest.raises(McpConfigError, match="sse"):
        build_connection("remote-srv", {"transport": "sse", "url": "https://example.com/sse"})


def test_missing_command_field_is_rejected() -> None:
    with pytest.raises(McpConfigError, match="command"):
        build_connection("srv", {})


def test_plain_env_value_without_var_syntax_passes_through() -> None:
    """Valor que não casa `${VAR}` é aceito como está (flags não-secretas)."""
    connection = build_connection("srv", {"command": "cmd", "env": {"DEBUG": "true"}})
    assert connection["env"] == {"DEBUG": "true"}  # type: ignore[typeddict-item]


# =========================================================================== #
# A2. build_connection — transporte http remoto (REQ-006 revisado, REQ-010)
#     Change `mcp-remote-http-transport`.
# =========================================================================== #
def test_parses_http_entry_without_command() -> None:
    """REQ-006: entrada http sem `command` é aceita, usando `url` em vez disso."""
    connection = build_connection("remote-srv", {"transport": "http", "url": "https://example.com/mcp"})
    assert connection["transport"] == "streamable_http"
    assert connection["url"] == "https://example.com/mcp"
    assert "command" not in connection


def test_http_entry_missing_url_is_rejected() -> None:
    """REQ-006: entrada http sem `url` é recusada com mensagem clara."""
    with pytest.raises(McpConfigError, match="url"):
        build_connection("remote-srv", {"transport": "http"})


def test_http_headers_resolve_env_var_reference(monkeypatch: pytest.MonkeyPatch) -> None:
    """REQ-010: valor de `headers` no formato `${VAR}` é resolvido do mesmo
    jeito que `env` (REQ-007) — nenhum segredo em texto puro no JSON."""
    monkeypatch.setenv("JEFF_TEST_MCP_HEADER_SECRET", "Bearer s3cr3t-token")
    connection = build_connection(
        "remote-srv",
        {
            "transport": "http",
            "url": "https://example.com/mcp",
            "headers": {"Authorization": "${JEFF_TEST_MCP_HEADER_SECRET}"},
        },
    )
    assert connection["headers"] == {"Authorization": "Bearer s3cr3t-token"}  # type: ignore[typeddict-item]


def test_http_header_raises_when_referenced_env_var_is_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """REQ-010: `${VAR}` referenciado em `headers` mas não definido levanta
    `McpConfigError` — mesmo comportamento hoje aplicado a `env` (REQ-007)."""
    monkeypatch.delenv("JEFF_TEST_MCP_HEADER_MISSING", raising=False)
    with pytest.raises(McpConfigError, match="JEFF_TEST_MCP_HEADER_MISSING"):
        build_connection(
            "remote-srv",
            {
                "transport": "http",
                "url": "https://example.com/mcp",
                "headers": {"Authorization": "${JEFF_TEST_MCP_HEADER_MISSING}"},
            },
        )


def test_http_entry_without_headers_field_has_no_extra_headers() -> None:
    """REQ-010: `headers` é opcional — entrada http sem ele monta a conexão
    sem headers extras, não é erro."""
    connection = build_connection("remote-srv", {"transport": "http", "url": "https://example.com/mcp"})
    assert connection["headers"] is None  # type: ignore[typeddict-item]


# =========================================================================== #
# A3. load_mcp_server_config — escopo por usuário (REQ-009 revisado, change
#     `user-scoped-mcp-config-storage`, task `task-client-1`). Delega a
#     `mcp_config_store.list_servers`, testado aqui via `_FakeRepository`
#     (mesmo padrão de `test_mcp_config_store.py`), nunca contra Postgres real.
# =========================================================================== #
async def test_load_mcp_server_config_returns_empty_for_user_with_no_servers(
    repo: _FakeRepository,
) -> None:
    """Usuário sem servidores configurados recebe `{}` — não é erro (mesmo
    estado default de hoje, agora por usuário em vez de arquivo ausente)."""
    connections = await load_mcp_server_config(str(uuid.uuid4()), repository=repo)
    assert connections == {}


async def test_load_mcp_server_config_isolates_by_user(repo: _FakeRepository) -> None:
    """unit-1: dois usuários com servidores diferentes nunca vazam um para o
    outro — só as linhas do `user_id` pedido entram no resultado."""
    user_a = str(uuid.uuid4())
    user_b = str(uuid.uuid4())
    await add_server(user_a, "srv-a", command="cmd-a", repository=repo)
    await add_server(user_b, "srv-b", command="cmd-b", repository=repo)

    connections = await load_mcp_server_config(user_a, repository=repo)

    assert set(connections) == {"srv-a"}
    assert connections["srv-a"]["command"] == "cmd-a"  # type: ignore[typeddict-item]


# =========================================================================== #
# B. list_mcp_tools — conexão real, degradação (REQ-004)
# =========================================================================== #
async def test_list_mcp_tools_empty_connections_returns_empty() -> None:
    tools, errors = await list_mcp_tools({})
    assert tools == []
    assert errors == []


async def test_list_mcp_tools_connects_to_real_local_server_and_lists_tools() -> None:
    """O teste pedido pela task: conectar a um servidor MCP local (stdio,
    subprocesso real) e listar as tools que ele expõe."""
    connections = {
        "jeff-ai-test-server": {
            "transport": "stdio",
            "command": sys.executable,
            "args": [str(_FIXTURE_SERVER)],
        }
    }
    tools, errors = await list_mcp_tools(connections)  # type: ignore[arg-type]

    assert errors == []
    names = {t.name for t in tools}
    assert names == {"echo", "add"}


async def test_list_mcp_tools_isolates_per_server_failure() -> None:
    """REQ-004: um servidor com comando inexistente NÃO impede os demais
    de conectar — a falha vira uma entrada em `errors`, não uma exceção
    que aborta a listagem inteira."""
    connections = {
        "broken-server": {
            "transport": "stdio",
            "command": "/definitely/not/a/real/executable-xyz",
            "args": [],
        },
        "jeff-ai-test-server": {
            "transport": "stdio",
            "command": sys.executable,
            "args": [str(_FIXTURE_SERVER)],
        },
    }
    tools, errors = await list_mcp_tools(connections)  # type: ignore[arg-type]

    assert len(errors) == 1
    assert isinstance(errors[0], McpServerConnectionError)
    assert errors[0].server_name == "broken-server"

    # O servidor bom continua funcionando apesar do outro ter falhado.
    names = {t.name for t in tools}
    assert names == {"echo", "add"}


async def test_connection_error_message_does_not_embed_secret_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REQ-007: a mensagem de erro que NÓS construímos nunca inclui o valor
    resolvido de uma credencial — só o nome do servidor e o erro do cliente
    MCP (que, para um comando inexistente, não menciona `env` de jeito
    nenhum)."""
    monkeypatch.setenv("JEFF_TEST_MCP_SECRET_2", "top-secret-do-not-leak")
    connections = {
        "broken-with-secret": {
            "transport": "stdio",
            "command": "/definitely/not/a/real/executable-xyz",
            "args": [],
            "env": {"API_KEY": "top-secret-do-not-leak"},
        }
    }
    tools, errors = await list_mcp_tools(connections)  # type: ignore[arg-type]

    assert tools == []
    assert len(errors) == 1
    assert "top-secret-do-not-leak" not in str(errors[0])


# =========================================================================== #
# C. list_mcp_tools — servidor http remoto real (REQ-004, REQ-010)
#    Change `mcp-remote-http-transport`. Mesmo princípio da seção B, mas com
#    transporte `http`: sobe `mcp_test_http_server.py` como subprocesso real
#    (uvicorn), conecta via `StreamableHttpConnection` de verdade.
# =========================================================================== #
def _find_free_port() -> int:
    """Reserva uma porta livre (bind + close) — evita hardcoded ports flaky."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_until_listening(port: int, *, timeout: float = 5.0) -> None:
    """Poll até a porta aceitar conexão TCP — evita corrida com o boot do uvicorn."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.1)
            try:
                s.connect(("127.0.0.1", port))
                return
            except OSError:
                time.sleep(0.05)
    raise TimeoutError(f"servidor de teste http não subiu na porta {port} em {timeout}s")


class _RunningHttpFixture:
    def __init__(self, port: int) -> None:
        self.port = port

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/mcp"


@contextlib.contextmanager
def _http_fixture_server(*, required_auth: str | None = None):
    """Sobe `mcp_test_http_server.py` como subprocesso real numa porta livre.

    `required_auth`, se dado, é repassado via env `MCP_TEST_REQUIRED_AUTH` —
    o fixture recusa (401) qualquer requisição cujo header `Authorization`
    não bata exatamente. Cleanup determinístico: `terminate()` + `wait()`
    com fallback pra `kill()`, sempre executado (bloco `finally`).
    """
    port = _find_free_port()
    env = dict(os.environ)
    if required_auth is not None:
        env["MCP_TEST_REQUIRED_AUTH"] = required_auth
    else:
        env.pop("MCP_TEST_REQUIRED_AUTH", None)

    process = subprocess.Popen(
        [sys.executable, str(_HTTP_FIXTURE_SERVER), str(port)],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait_until_listening(port)
        yield _RunningHttpFixture(port)
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


async def test_http_connection_with_correct_header_lists_tools() -> None:
    """Prova end-to-end do REQ-010: o header `Authorization` chega de fato
    na requisição HTTP recebida pelo servidor — não só que o código monta o
    header, mas que ele funciona ponta a ponta contra um servidor real."""
    expected_token = "Bearer jeff-ai-test-token-abc123"
    with _http_fixture_server(required_auth=expected_token) as server:
        connections = {
            "jeff-ai-http-test-server": {
                "transport": "streamable_http",
                "url": server.url,
                "headers": {"Authorization": expected_token},
            }
        }
        tools, errors = await list_mcp_tools(connections)  # type: ignore[arg-type]

    assert errors == []
    names = {t.name for t in tools}
    assert names == {"echo", "add"}


async def test_http_connection_with_wrong_header_fails_isolated() -> None:
    """Contraparte do teste acima — prova que o header realmente importa: um
    valor errado é recusado pelo servidor (401), e a falha fica isolada em
    `errors` (REQ-004), não uma exceção que aborta a listagem."""
    with _http_fixture_server(required_auth="Bearer the-real-token") as server:
        connections = {
            "jeff-ai-http-test-server": {
                "transport": "streamable_http",
                "url": server.url,
                "headers": {"Authorization": "Bearer wrong-token"},
            }
        }
        tools, errors = await list_mcp_tools(connections)  # type: ignore[arg-type]

    assert tools == []
    assert len(errors) == 1
    assert errors[0].server_name == "jeff-ai-http-test-server"


async def test_load_mcp_server_config_to_real_http_server_end_to_end(
    repo: _FakeRepository,
) -> None:
    """Cobre o pipeline inteiro, não só `list_mcp_tools` chamado direto:
    `mcp_config_store` (Postgres, por usuário) -> `load_mcp_server_config`
    (resolve) -> `list_mcp_tools` -> conexão HTTP real contra um servidor de
    verdade. `headers` já chega resolvido (valor real, não `${VAR}`) —
    convenção do armazenamento em banco (design Decision 2)."""
    expected_token = "Bearer end-to-end-token-xyz"
    user_id = str(uuid.uuid4())

    with _http_fixture_server(required_auth=expected_token) as server:
        await add_server(
            user_id,
            "jeff-ai-http-test-server",
            transport="http",
            url=server.url,
            headers={"Authorization": expected_token},
            repository=repo,
        )
        connections = await load_mcp_server_config(user_id, repository=repo)
        tools, errors = await list_mcp_tools(connections)

    assert errors == []
    names = {t.name for t in tools}
    assert names == {"echo", "add"}
