"""Servidor MCP mínimo (stdio) usado por `test_mcp_client.py`.

Não é parte do produto — é um fixture de teste que roda como subprocesso
real (via `StdioConnection`), para que `test_mcp_client.py` exercite a
conexão de verdade (`MultiServerMCPClient`), não um mock do transporte.
"""
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("jeff-ai-test-server")


@mcp.tool()
def echo(text: str) -> str:
    """Devolve `text` sem modificação. Usado para provar que a tool é chamável."""
    return text


@mcp.tool()
def add(a: int, b: int) -> int:
    """Soma dois inteiros."""
    return a + b


if __name__ == "__main__":
    mcp.run(transport="stdio")
