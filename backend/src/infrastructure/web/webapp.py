"""FastAPI customizado montado pelo backend LangGraph via `http.app`.

Consolida as rotas de mídia e documentos Office (imagens geradas, imagens de
referência e downloads de docx/xlsx/pptx) no mesmo processo/porta que serve o
grafo `unified`, substituindo o container `image-server` separado para essas
rotas.

Desde `retire-image-server-task-core-1`, este módulo também monta
`mcp_admin_router` (`/api/mcp/*`) — o antigo processo `image_server.py`
separado foi aposentado. A garantia de que nenhuma tool do agente alcança
essas rotas (REQ-001/REQ-008 do capability `mcp-client`) deixou de depender
de isolamento físico de processo e passou a depender de `require_auth`
(sessão de usuário válida, obrigatória globalmente neste app) — nenhuma tool
registrada no agente tem acesso ao cookie de sessão do browser, então nenhuma
delas consegue autenticar contra essas rotas mesmo estando no mesmo processo.
`test_mcp_admin_import_boundary.py` reforça isso separadamente: nenhum módulo
de `src/tools`/`src/agents`/`src/composition` (fora dos dois arquivos admin)
pode sequer importar `mcp_admin_api`/`mcp_config_store`.

`require_auth` é registrada como dependency GLOBAL do app (task-rest-3):
toda rota — existente ou futura — exige sessão válida por padrão, exceto as
que correspondem a `PUBLIC_PATHS` (checado dentro da própria dependency).
Isso inclui `images_router`/`documents_router`, que antes eram públicos.
"""

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI

from src.agents.unified.mcp_admin_api import router as mcp_admin_router
from src.domain.scheduling import TaskStatus
from src.infrastructure.attachments.schema import (
    ensure_schema as ensure_attachments_schema,
)
from src.infrastructure.auth.db import close_pool, init_pool
from src.infrastructure.auth.dependencies import require_auth
from src.infrastructure.auth.schema import init_auth_schema
from src.infrastructure.ownership.schema import ensure_schema as ensure_ownership_schema
from src.infrastructure.persistence.scheduled_task_repository import (
    PostgresScheduledTaskRepository,
)
from src.infrastructure.persistence.telegram_link_codes_schema import (
    ensure_schema as ensure_telegram_link_codes_schema,
)
from src.infrastructure.persistence.user_integrations_schema import (
    ensure_schema as ensure_user_integrations_schema,
)
from src.infrastructure.persistence.user_mcp_servers_schema import (
    ensure_schema as ensure_user_mcp_servers_schema,
)
from src.infrastructure.persistence.whatsapp_link_codes_schema import (
    ensure_schema as ensure_whatsapp_link_codes_schema,
)
from src.infrastructure.scheduling.scheduler_instance import task_scheduler
from src.infrastructure.usage.schema import ensure_schema as ensure_usage_schema
from src.infrastructure.web.admin_users_router import router as admin_users_router
from src.infrastructure.web.attachments_router import router as attachments_router
from src.infrastructure.web.auth_router import router as auth_router
from src.infrastructure.web.documents_router import router as documents_router
from src.infrastructure.web.images_router import router as images_router
from src.infrastructure.web.integrations_router import router as integrations_router
from src.infrastructure.web.media_delivery_router import router as media_delivery_router
from src.infrastructure.web.scheduling_router import router as scheduling_router
from src.infrastructure.web.usage_router import router as usage_router
from src.infrastructure.web.whatsapp_webhook_router import (
    router as whatsapp_webhook_router,
)
from src.infrastructure.whatsapp.schema import (
    ensure_whatsapp_threads_schema,
)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Garante as tabelas `users`/`sessions`/`generated_files`/`chat_attachments`/`token_usage_events`/`user_integrations`/`telegram_link_codes`/`whatsapp_link_codes`, o bootstrap do admin e o pool de auth.

    Falha o startup com erro explícito se `POSTGRES_URI` ou as credenciais de
    admin (`ADMIN_USERNAME`/`ADMIN_PASSWORD_HASH`) estiverem ausentes numa
    tabela `users` vazia — não deve haver um fallback silencioso sem admin.
    `generated_files` e `chat_attachments` dependem de `users` já existir (FK),
    por isso rodam depois de `init_auth_schema`. `token_usage_events` não tem
    FK; sobe aqui para existir antes dos primeiros records do callback.
    `user_integrations`/`telegram_link_codes` também dependem de `users` (FK)
    — schemas do change `user-integration-credentials`, nunca chamados aqui
    antes (`whatsapp-evolution-channel-task-prereq-1`), o que deixava
    `integrations_router` funcionalmente quebrado mesmo montado.
    `whatsapp_link_codes` (`whatsapp-evolution-channel-task-linking-2`) segue
    o mesmo motivo de `telegram_link_codes`: sem o schema, o endpoint de
    geração de código de vínculo WhatsApp quebraria no primeiro INSERT.
    `whatsapp_threads` sofria do mesmo problema: `ensure_whatsapp_threads_schema`
    existia em `src/infrastructure/whatsapp/schema.py` mas nunca era chamada,
    quebrando `get_or_create_thread_id` com `UndefinedTable` na primeira
    mensagem recebida após o vínculo do número.
    `user_mcp_servers` (change `user-scoped-mcp-config-storage`) segue o
    mesmo motivo de `user_integrations`: também depende de `users` (FK).

    `task_scheduler.start()` + `_reschedule_pending_tasks` (achado 2026-08-04):
    o `AsyncIOScheduler` usa o `MemoryJobStore` padrão (sem persistência) e,
    além disso, nada no processo chamava `.start()` — jobs ficavam "adicionados
    tentativamente" para sempre, nunca disparando. Mesmo corrigindo o
    `.start()`, todo restart do processo esvazia o job store em memória, então
    o boot precisa reconstruir os triggers a partir do Postgres (fonte da
    verdade) para as tarefas que ainda estão `SCHEDULED`.
    """
    # ChannelRegistry do processo webapp — web + telegram + whatsapp
    # (unify-message-delivery-pipeline composition-1 / REQ-002 chat-channel-port).
    # Deve rodar antes de qualquer request/webhook que resolva um canal.
    from src.composition.dependencies import build_dependencies

    build_dependencies()

    conninfo = os.environ["POSTGRES_URI"]
    init_auth_schema(conninfo)
    ensure_ownership_schema(conninfo)
    ensure_attachments_schema(conninfo)
    ensure_usage_schema(conninfo)
    ensure_user_integrations_schema(conninfo)
    ensure_user_mcp_servers_schema(conninfo)
    ensure_telegram_link_codes_schema(conninfo)
    ensure_whatsapp_link_codes_schema(conninfo)
    ensure_whatsapp_threads_schema(conninfo)
    await init_pool(conninfo)
    await _reschedule_pending_tasks(conninfo)
    task_scheduler.start()
    try:
        yield
    finally:
        task_scheduler.shutdown(wait=False)
        await close_pool()


async def _reschedule_pending_tasks(conninfo: str) -> None:
    """Re-registra no scheduler em memória os triggers de tarefas ainda `SCHEDULED`.

    Sem isso, uma tarefa criada antes do último restart do processo fica
    presa em `SCHEDULED` para sempre — existe no Postgres, mas o
    `AsyncIOScheduler` não tem mais o job em memória e nunca vai chamá-la.
    """
    repo = PostgresScheduledTaskRepository(conninfo)
    for task in await repo.list_all():
        if task.status is TaskStatus.SCHEDULED:
            await task_scheduler.schedule(task)


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

# Rota de upload de anexos de chat (imagem/pdf/docx/xlsx/csv/txt).
app.include_router(attachments_router)

# Entrega de attachments de saída (WhatsApp) por token de uso único — sob
# /public/, isenta de require_auth. `evolution_client.send_media` só aceita
# `media` como URL (não base64), e /api/files·/api/images exigem sessão.
app.include_router(media_delivery_router)

# Agregação admin de uso de tokens (GET /api/usage).
app.include_router(usage_router)

# CRUD de credenciais de integração por usuário (Telegram, WhatsApp Business,
# SMTP) + geração de código de vínculo do Telegram/WhatsApp.
app.include_router(integrations_router)

# Webhook da Evolution API (canal WhatsApp, número central — Modelo B).
app.include_router(whatsapp_webhook_router)

# API administrativa de servidores MCP (change `retire-image-server`, antes
# num processo `image_server.py` separado). `require_auth` já é global neste
# app; o router também carrega sua própria dependency (redundante, inofensiva
# — ver comentário em `mcp_admin_api.py`).
app.include_router(mcp_admin_router)

# API administrativa de usuários (`GET`/`POST /admin/users`, `PATCH
# /admin/users/{id}` com guarda-corpo de auto-lockout traduzido pra 409 —
# change `user-management`, task-api-1..4). `dependencies=[Depends(require_admin)]`
# no próprio router (não global): só estas rotas exigem `role=admin`.
app.include_router(admin_users_router)

# CRUD de tarefas agendadas (`GET`/`POST`/`PATCH`/`DELETE /api/scheduled-tasks`
# — spec `scheduled-tasks-rest-api`). Router existia desde `e04dceb` mas nunca
# foi montado aqui, deixando o frontend (`frontend/src/lib/scheduling.ts`)
# receber 404 em toda chamada, mesmo com tarefas já criadas via
# `scheduling_tools.py` (tool do agente, que chama o use case direto e nunca
# passou por este router).
app.include_router(scheduling_router)
