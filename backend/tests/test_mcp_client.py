"""Testes do cliente MCP básico (task `unified-agent-realignment-task-mcp-1`).

Cobre REQ-001, REQ-004, REQ-006, REQ-007 do `mcp-client`. O teste de conexão
real (`test_list_mcp_tools_connects_to_real_local_server`) roda um servidor
MCP de verdade como subprocesso (`tests/fixtures/mcp_test_server.py`), não um
mock do transporte — é o "Teste: conectar a um servidor MCP local e listar
as tools" pedido na task.

A seção C (`mcp-remote-http-transport`) espelha esse mesmo princípio pro
transporte `http`: `tests/fixtures/mcp_test_http_server.py` sobe um servidor
real via `uvicorn`, e os testes conectam via HTTP de verdade — não mockado.
"""
from __future__ import annotations

import contextlib
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

from src.agents.unified.mcp_client import (
    McpConfigError,
    McpServerConnectionError,
    list_mcp_tools,
    load_mcp_server_config,
)

_FIXTURE_SERVER = Path(__file__).parent / "fixtures" / "mcp_test_server.py"
_HTTP_FIXTURE_SERVER = Path(__file__).parent / "fixtures" / "mcp_test_http_server.py"


# =========================================================================== #
# A. load_mcp_server_config — REQ-001, REQ-006, REQ-007
# =========================================================================== #
def test_missing_config_file_returns_empty(tmp_path: Path) -> None:
    """Arquivo ausente não é erro — é o estado default (REQ-001)."""
    assert load_mcp_server_config(tmp_path / "does-not-exist.json") == {}


def test_parses_stdio_entry(tmp_path: Path) -> None:
    """Também serve como cenário de regressão do REQ-006 revisado: `stdio`
    (default, sem `transport`) continua funcionando sem mudança de
    comportamento agora que `http` também é suportado."""
    config = tmp_path / "mcp_servers.json"
    config.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "my-server": {
                        "command": "npx",
                        "args": ["-y", "@some/server"],
                    }
                }
            }
        )
    )
    connections = load_mcp_server_config(config)
    assert connections["my-server"]["transport"] == "stdio"
    assert connections["my-server"]["command"] == "npx"
    assert connections["my-server"]["args"] == ["-y", "@some/server"]


def test_resolves_env_var_reference(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """REQ-007: `${VAR}` é substituído por `os.environ`, nunca hardcoded."""
    monkeypatch.setenv("JEFF_TEST_MCP_SECRET", "s3cr3t-value")
    config = tmp_path / "mcp_servers.json"
    config.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "srv": {
                        "command": "some-cmd",
                        "env": {"API_KEY": "${JEFF_TEST_MCP_SECRET}"},
                    }
                }
            }
        )
    )
    connections = load_mcp_server_config(config)
    assert connections["srv"]["env"] == {"API_KEY": "s3cr3t-value"}  # type: ignore[typeddict-item]


def test_raises_when_referenced_env_var_is_unset(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("JEFF_TEST_MCP_MISSING", raising=False)
    config = tmp_path / "mcp_servers.json"
    config.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "srv": {
                        "command": "some-cmd",
                        "env": {"API_KEY": "${JEFF_TEST_MCP_MISSING}"},
                    }
                }
            }
        )
    )
    with pytest.raises(McpConfigError, match="JEFF_TEST_MCP_MISSING"):
        load_mcp_server_config(config)


def test_unsupported_transport_is_rejected_explicitly(tmp_path: Path) -> None:
    """REQ-006: transporte fora de escopo (`http` NÃO conta mais — ver
    `test_parses_http_entry_without_command`) é recusado com mensagem clara,
    não ignorado."""
    config = tmp_path / "mcp_servers.json"
    config.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "remote-srv": {
                        "transport": "sse",
                        "url": "https://example.com/sse",
                    }
                }
            }
        )
    )
    with pytest.raises(McpConfigError, match="sse"):
        load_mcp_server_config(config)


def test_missing_command_field_is_rejected(tmp_path: Path) -> None:
    config = tmp_path / "mcp_servers.json"
    config.write_text(json.dumps({"mcpServers": {"srv": {}}}))
    with pytest.raises(McpConfigError, match="command"):
        load_mcp_server_config(config)


def test_plain_env_value_without_var_syntax_passes_through(tmp_path: Path) -> None:
    """Valor que não casa `${VAR}` é aceito como está (flags não-secretas)."""
    config = tmp_path / "mcp_servers.json"
    config.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "srv": {"command": "cmd", "env": {"DEBUG": "true"}},
                }
            }
        )
    )
    connections = load_mcp_server_config(config)
    assert connections["srv"]["env"] == {"DEBUG": "true"}  # type: ignore[typeddict-item]


# =========================================================================== #
# A2. load_mcp_server_config — transporte http remoto (REQ-006 revisado, REQ-010)
#     Change `mcp-remote-http-transport`.
# =========================================================================== #
def test_parses_http_entry_without_command(tmp_path: Path) -> None:
    """REQ-006: entrada http sem `command` é aceita, usando `url` em vez disso."""
    config = tmp_path / "mcp_servers.json"
    config.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "remote-srv": {
                        "transport": "http",
                        "url": "https://example.com/mcp",
                    }
                }
            }
        )
    )
    connections = load_mcp_server_config(config)
    entry = connections["remote-srv"]
    assert entry["transport"] == "streamable_http"
    assert entry["url"] == "https://example.com/mcp"
    assert "command" not in entry


def test_http_entry_missing_url_is_rejected(tmp_path: Path) -> None:
    """REQ-006: entrada http sem `url` é recusada com mensagem clara."""
    config = tmp_path / "mcp_servers.json"
    config.write_text(json.dumps({"mcpServers": {"remote-srv": {"transport": "http"}}}))
    with pytest.raises(McpConfigError, match="url"):
        load_mcp_server_config(config)


def test_http_headers_resolve_env_var_reference(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """REQ-010: valor de `headers` no formato `${VAR}` é resolvido do mesmo
    jeito que `env` (REQ-007) — nenhum segredo em texto puro no JSON."""
    monkeypatch.setenv("JEFF_TEST_MCP_HEADER_SECRET", "Bearer s3cr3t-token")
    config = tmp_path / "mcp_servers.json"
    config.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "remote-srv": {
                        "transport": "http",
                        "url": "https://example.com/mcp",
                        "headers": {"Authorization": "${JEFF_TEST_MCP_HEADER_SECRET}"},
                    }
                }
            }
        )
    )
    connections = load_mcp_server_config(config)
    assert connections["remote-srv"]["headers"] == {"Authorization": "Bearer s3cr3t-token"}  # type: ignore[typeddict-item]


def test_http_header_raises_when_referenced_env_var_is_unset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """REQ-010: `${VAR}` referenciado em `headers` mas não definido levanta
    `McpConfigError` — mesmo comportamento hoje aplicado a `env` (REQ-007)."""
    monkeypatch.delenv("JEFF_TEST_MCP_HEADER_MISSING", raising=False)
    config = tmp_path / "mcp_servers.json"
    config.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "remote-srv": {
                        "transport": "http",
                        "url": "https://example.com/mcp",
                        "headers": {"Authorization": "${JEFF_TEST_MCP_HEADER_MISSING}"},
                    }
                }
            }
        )
    )
    with pytest.raises(McpConfigError, match="JEFF_TEST_MCP_HEADER_MISSING"):
        load_mcp_server_config(config)


def test_http_entry_without_headers_field_has_no_extra_headers(tmp_path: Path) -> None:
    """REQ-010: `headers` é opcional — entrada http sem ele monta a conexão
    sem headers extras, não é erro."""
    config = tmp_path / "mcp_servers.json"
    config.write_text(
        json.dumps({"mcpServers": {"remote-srv": {"transport": "http", "url": "https://example.com/mcp"}}})
    )
    connections = load_mcp_server_config(config)
    assert connections["remote-srv"]["headers"] is None  # type: ignore[typeddict-item]


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
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cobre o pipeline inteiro, não só `list_mcp_tools` chamado direto:
    `mcp_servers.json` (`${VAR}`) -> `load_mcp_server_config` (resolve) ->
    `list_mcp_tools` -> conexão HTTP real contra um servidor de verdade."""
    expected_token = "Bearer end-to-end-token-xyz"
    monkeypatch.setenv("JEFF_TEST_MCP_HTTP_TOKEN", expected_token)

    with _http_fixture_server(required_auth=expected_token) as server:
        config = tmp_path / "mcp_servers.json"
        config.write_text(
            json.dumps(
                {
                    "mcpServers": {
                        "jeff-ai-http-test-server": {
                            "transport": "http",
                            "url": server.url,
                            "headers": {"Authorization": "${JEFF_TEST_MCP_HTTP_TOKEN}"},
                        }
                    }
                }
            )
        )
        connections = load_mcp_server_config(config)
        tools, errors = await list_mcp_tools(connections)

    assert errors == []
    names = {t.name for t in tools}
    assert names == {"echo", "add"}
