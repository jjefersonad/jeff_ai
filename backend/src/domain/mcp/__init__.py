"""Domínio de servidores MCP por usuário — entidade `McpServerConfig`.

PURO: zero import de framework. Persistência (cifra de `env`/`headers`
incluída) fica em `infrastructure/`; validação de forma por `transport` fica
na fronteira da aplicação (`src/application/mcp/`).
"""
from src.domain.mcp.mcp_server_config import McpServerConfig

__all__ = ["McpServerConfig"]
