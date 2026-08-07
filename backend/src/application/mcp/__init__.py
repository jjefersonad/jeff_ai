"""Aplicação — servidores MCP por usuário.

`McpServerEntryConfig` valida a forma de uma entrada `mcpServers` (stdio ou
http) na fronteira de escrita, antes de qualquer persistência.
"""
from src.application.mcp.mcp_server_schema import McpServerEntryConfig

__all__ = ["McpServerEntryConfig"]
