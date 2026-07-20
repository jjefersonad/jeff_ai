"""Servidor MCP mínimo (streamable HTTP) usado por `test_mcp_client.py`.

Não é parte do produto — é um fixture de teste que roda como subprocesso
real, ouvindo HTTP de verdade (via `uvicorn`), para que os testes da change
`mcp-remote-http-transport` exercitem a conexão de verdade
(`StreamableHttpConnection` -> `MultiServerMCPClient`), não um mock do
transporte. Espelha o papel de `mcp_test_server.py` (variante stdio).

## Verificação do header Authorization

Para provar que `headers` configurado via `${VAR}` chega de fato na
requisição HTTP (REQ-010), este fixture opcionalmente exige um valor exato
de `Authorization`, lido da variável de ambiente `MCP_TEST_REQUIRED_AUTH`.
Se definida e o header recebido não bater, a requisição é recusada com 401
ANTES de chegar no app MCP — uma falha de conexão do lado do cliente prova
que o header não foi enviado (ou foi enviado errado); um sucesso prova que
foi enviado e bateu.
"""
from __future__ import annotations

import os
import sys

import uvicorn
from mcp.server.fastmcp import FastMCP
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

mcp = FastMCP("jeff-ai-test-http-server", host="127.0.0.1")


@mcp.tool()
def echo(text: str) -> str:
    """Devolve `text` sem modificação. Usado para provar que a tool é chamável."""
    return text


@mcp.tool()
def add(a: int, b: int) -> int:
    """Soma dois inteiros."""
    return a + b


class _RequireAuthHeaderMiddleware(BaseHTTPMiddleware):
    """Recusa a requisição com 401 se `Authorization` não bater com o esperado.

    Curto-circuita ANTES do app MCP — a checagem acontece na borda HTTP,
    igual um servidor MCP remoto real faria.
    """

    def __init__(self, app, *, required_auth: str) -> None:
        super().__init__(app)
        self._required_auth = required_auth

    async def dispatch(self, request: Request, call_next):
        received = request.headers.get("authorization")
        if received != self._required_auth:
            return JSONResponse(
                {"error": "unauthorized", "received": received},
                status_code=401,
            )
        return await call_next(request)


def _build_app(*, required_auth: str | None):
    app = mcp.streamable_http_app()
    if required_auth:
        app.add_middleware(_RequireAuthHeaderMiddleware, required_auth=required_auth)
    return app


if __name__ == "__main__":
    port = int(sys.argv[1])
    required_auth = os.environ.get("MCP_TEST_REQUIRED_AUTH") or None
    asgi_app = _build_app(required_auth=required_auth)
    uvicorn.run(asgi_app, host="127.0.0.1", port=port, log_level="warning")
