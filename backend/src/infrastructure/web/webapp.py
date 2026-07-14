"""FastAPI customizado montado pelo backend LangGraph via `http.app`.

Consolida as rotas de mídia e documentos Office (imagens geradas, imagens de
referência e downloads de docx/xlsx/pptx) no mesmo processo/porta que serve o
grafo `unified`, substituindo o container `image-server` separado para essas
rotas.

IMPORTANTE: este módulo NÃO importa `mcp_admin_api` e NÃO monta `/api/mcp/*`.
As rotas administrativas de servidores MCP continuam em um processo separado
do grafo do agente, preservando a garantia de que nenhuma tool do agente pode
alcançá-las (REQ-001 do capability `mcp-client`).
"""

from fastapi import FastAPI

from src.infrastructure.web.documents_router import router as documents_router
from src.infrastructure.web.images_router import router as images_router

app = FastAPI(title="Jeff AI Web", version="1.0.0")

# Rotas de imagens geradas + upload/serve de referências.
app.include_router(images_router)

# Rotas de download de documentos Office (docx/xlsx/pptx).
app.include_router(documents_router)
