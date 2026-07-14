"""Servidor HTTP minimalista para o router administrativo de servidores MCP.

Vive em um processo `python:3.11-slim` separado do grafo do agente
(`unified`, servido pelo backend LangGraph). Esta é a fronteira que cumpre
REQ-001 do capability `mcp-client` ("o agente não consegue adicionar/remover/
modificar servidores MCP por conta própria"): o processo que roda o agente
nunca importa este módulo nem monta estas rotas. Só o frontend (humano, via
browser) fala com `/api/mcp/*`.

As rotas de mídia e documentos (`/api/images*`, `/api/references*`,
`/api/files/{kind}/{filename}`) foram migradas para o `http.app` do backend
LangGraph em `src/infrastructure/web/webapp.py` (change
`consolidate-http-routes-langgraph`). Este servidor NÃO as serve.
"""

import os
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Torna o pacote `src` importável (montado ao lado deste arquivo no container).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from src.agents.unified.mcp_admin_api import router as mcp_admin_router  # noqa: E402

app = FastAPI(title="Jeff AI MCP Admin", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API administrativa de servidores MCP (task `unified-agent-realignment-task-mcp-3`).
# Vive neste processo — separado do grafo do agente — para que nenhuma tool do
# agente possa alcançar estas rotas (REQ-001 do `mcp-client`).
app.include_router(mcp_admin_router)


@app.get("/health")
async def health():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
