"""FastAPI customizado montado pelo backend LangGraph via `http.app`.

Consolida as rotas de mídia e documentos Office (imagens geradas, imagens de
referência e downloads de docx/xlsx/pptx) no mesmo processo/porta que serve o
grafo `unified`, substituindo o container `image-server` separado para essas
rotas.

IMPORTANTE: este módulo NÃO importa `mcp_admin_api` e NÃO monta `/api/mcp/*`.
As rotas administrativas de servidores MCP continuam em um processo separado
do grafo do agente, preservando a garantia de que nenhuma tool do agente pode
alcançá-las (REQ-001 do capability `mcp-client`).

`require_auth` é registrada como dependency GLOBAL do app (task-rest-3):
toda rota — existente ou futura — exige sessão válida por padrão, exceto as
que correspondem a `PUBLIC_PATHS` (checado dentro da própria dependency).
Isso inclui `images_router`/`documents_router`, que antes eram públicos.
"""

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI

from src.infrastructure.auth.db import close_pool, init_pool
from src.infrastructure.auth.dependencies import require_auth
from src.infrastructure.auth.schema import init_auth_schema
from src.infrastructure.web.auth_router import router as auth_router
from src.infrastructure.web.documents_router import router as documents_router
from src.infrastructure.web.images_router import router as images_router


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Garante as tabelas `users`/`sessions`, o bootstrap do admin inicial e o pool de auth.

    Falha o startup com erro explícito se `POSTGRES_URI` ou as credenciais de
    admin (`ADMIN_USERNAME`/`ADMIN_PASSWORD_HASH`) estiverem ausentes numa
    tabela `users` vazia — não deve haver um fallback silencioso sem admin.
    """
    conninfo = os.environ["POSTGRES_URI"]
    init_auth_schema(conninfo)
    await init_pool(conninfo)
    try:
        yield
    finally:
        await close_pool()


app = FastAPI(
    title="Jeff AI Web",
    version="1.0.0",
    lifespan=_lifespan,
    dependencies=[Depends(require_auth)],
)

# Rotas públicas de autenticação (POST /public/login, POST /public/logout).
app.include_router(auth_router)

# Rotas de imagens geradas + upload/serve de referências.
app.include_router(images_router)

# Rotas de download de documentos Office (docx/xlsx/pptx).
app.include_router(documents_router)
