"""Testes de `mcp_config_store` (task `unified-agent-realignment-task-mcp-3`).

Cobre REQ-001 do `mcp-client`: "o usuário adiciona, edita e remove
servidores MCP" — via este módulo, consumido só pela API administrativa
(`mcp_admin_api.py`), nunca pelo agente.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.agents.unified.mcp_config_store import (
    McpServerConfigError,
    add_server,
    delete_server,
    get_server,
    list_servers,
    update_server,
)


def test_list_servers_on_missing_file_is_empty(tmp_path: Path) -> None:
    assert list_servers(tmp_path / "missing.json") == {}


def test_add_server_writes_env_as_var_reference_not_value(tmp_path: Path) -> None:
    """REQ-007: a API recebe o NOME da env var, e grava a referência
    `${VAR}` — nunca um valor de segredo em texto plano."""
    path = tmp_path / "mcp_servers.json"
    entry = add_server(
        "meu-servidor",
        command="npx",
        args=["-y", "@some/server"],
        env_var_names={"API_KEY": "MEU_SERVIDOR_API_KEY"},
        path=path,
    )
    assert entry["env"] == {"API_KEY": "${MEU_SERVIDOR_API_KEY}"}
    assert entry["transport"] == "stdio"

    raw = json.loads(path.read_text())
    assert raw["mcpServers"]["meu-servidor"]["env"] == {"API_KEY": "${MEU_SERVIDOR_API_KEY}"}


def test_add_server_rejects_duplicate_name(tmp_path: Path) -> None:
    path = tmp_path / "mcp_servers.json"
    add_server("srv", command="cmd", path=path)
    with pytest.raises(McpServerConfigError, match="já existe"):
        add_server("srv", command="cmd", path=path)


def test_add_server_rejects_missing_command(tmp_path: Path) -> None:
    with pytest.raises(McpServerConfigError, match="command"):
        add_server("srv", command="", path=tmp_path / "mcp_servers.json")


def test_update_server_requires_existing_entry(tmp_path: Path) -> None:
    with pytest.raises(McpServerConfigError, match="não existe"):
        update_server("ghost", command="cmd", path=tmp_path / "mcp_servers.json")


def test_update_server_replaces_entry(tmp_path: Path) -> None:
    path = tmp_path / "mcp_servers.json"
    add_server("srv", command="npx", args=["-y", "a"], path=path)
    update_server("srv", command="npx", args=["-y", "b"], path=path)
    assert get_server("srv", path=path)["args"] == ["-y", "b"]


def test_delete_server_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "mcp_servers.json"
    add_server("srv", command="cmd", path=path)
    delete_server("srv", path=path)
    assert get_server("srv", path=path) is None
    delete_server("srv", path=path)  # não deve levantar


def test_multiple_servers_coexist(tmp_path: Path) -> None:
    path = tmp_path / "mcp_servers.json"
    add_server("a", command="cmd-a", path=path)
    add_server("b", command="cmd-b", path=path)
    servers = list_servers(path)
    assert set(servers) == {"a", "b"}
