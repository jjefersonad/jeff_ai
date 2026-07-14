"""Testes do cliente MCP básico (task `unified-agent-realignment-task-mcp-1`).

Cobre REQ-001, REQ-004, REQ-006, REQ-007 do `mcp-client`. O teste de conexão
real (`test_list_mcp_tools_connects_to_real_local_server`) roda um servidor
MCP de verdade como subprocesso (`tests/fixtures/mcp_test_server.py`), não um
mock do transporte — é o "Teste: conectar a um servidor MCP local e listar
as tools" pedido na task.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from src.agents.unified.mcp_client import (
    McpConfigError,
    McpServerConnectionError,
    list_mcp_tools,
    load_mcp_server_config,
)

_FIXTURE_SERVER = Path(__file__).parent / "fixtures" / "mcp_test_server.py"


# =========================================================================== #
# A. load_mcp_server_config — REQ-001, REQ-006, REQ-007
# =========================================================================== #
def test_missing_config_file_returns_empty(tmp_path: Path) -> None:
    """Arquivo ausente não é erro — é o estado default (REQ-001)."""
    assert load_mcp_server_config(tmp_path / "does-not-exist.json") == {}


def test_parses_stdio_entry(tmp_path: Path) -> None:
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
    assert connections["srv"]["env"] == {"API_KEY": "s3cr3t-value"}


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


def test_non_stdio_transport_is_rejected_explicitly(tmp_path: Path) -> None:
    """REQ-006: transporte fora de escopo é recusado com mensagem clara, não ignorado."""
    config = tmp_path / "mcp_servers.json"
    config.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "remote-srv": {
                        "transport": "http",
                        "command": "irrelevant",
                    }
                }
            }
        )
    )
    with pytest.raises(McpConfigError, match="http"):
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
    assert connections["srv"]["env"] == {"DEBUG": "true"}


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
