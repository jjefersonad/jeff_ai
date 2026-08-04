"""Testes de `src/application/mcp/mcp_server_schema.py`.

Cobre `user-scoped-mcp-config-storage-task-store-1-unit-1` (REQ-001 do spec
`user-mcp-server-store`): validação de escrita — mesma regra que
`mcp_client.build_connection` já aplica em tempo de conexão (`command`
obrigatório para `stdio`, `url` obrigatório para `http`), mas aplicada mais
cedo, no momento de gravar a configuração.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.application.mcp.mcp_server_schema import McpServerEntryConfig


def test_stdio_entry_without_command_raises() -> None:
    with pytest.raises(ValidationError):
        McpServerEntryConfig(transport="stdio", args=["-y"])


def test_http_entry_without_url_raises() -> None:
    with pytest.raises(ValidationError):
        McpServerEntryConfig(transport="http", headers={"Authorization": "Bearer x"})


def test_valid_stdio_entry_round_trips_fields() -> None:
    entry = McpServerEntryConfig(
        transport="stdio",
        command="npx",
        args=["-y", "@algum/mcp-server"],
        env={"API_KEY": "MEU_SEGREDO"},
    )

    assert entry.transport == "stdio"
    assert entry.command == "npx"
    assert entry.args == ["-y", "@algum/mcp-server"]
    assert entry.env == {"API_KEY": "MEU_SEGREDO"}


def test_valid_http_entry_round_trips_fields() -> None:
    entry = McpServerEntryConfig(
        transport="http",
        url="https://exemplo.com/mcp",
        headers={"Authorization": "Bearer x"},
    )

    assert entry.transport == "http"
    assert entry.url == "https://exemplo.com/mcp"
    assert entry.headers == {"Authorization": "Bearer x"}
