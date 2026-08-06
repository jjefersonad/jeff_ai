"""Fiação manual (DI) dos casos de uso com adapters concretos de infraestrutura.

Ponto ÚNICO onde a escolha do adapter concreto acontece. Trocar uma implementação
(ex.: outro provedor de imagem, outro sink) muda apenas este módulo — os casos de
uso e o domínio permanecem intactos, pois dependem só dos ports.

Camada de composição (frameworks & drivers): é o único lugar que conhece ao mesmo
tempo os use cases (application) e os adapters concretos (infrastructure).
"""
from __future__ import annotations

import os
from collections.abc import Awaitable, Callable
from pathlib import Path

from langgraph.config import get_store

from src.application.ports.document_writer import DocumentWriterPort
from src.application.ports.reference_image_fetch import ReferenceImageFetchPort
from src.application.use_cases import (
    CancelScheduledTask,
    CreateDocument,
    CreateScheduledTask,
    GenerateRequirementsDocument,
    GetNextFeatureNumber,
    ListScheduledTasks,
    PlanAndCreateImage,
)
from src.infrastructure.channels.registry import ChannelRegistry
from src.infrastructure.channels.telegram_channel import TelegramChannel
from src.infrastructure.channels.web_channel import WebChannel
from src.infrastructure.channels.whatsapp_channel import WhatsAppChannel
from src.infrastructure.documents import DocxWriter
from src.infrastructure.filesystem.filesystem_document_sink import (
    FilesystemDocumentSink,
)
from src.infrastructure.filesystem.filesystem_sdd_artifact_store import (
    FilesystemSddArtifactStore,
)
from src.infrastructure.llm.gemini_image_adapter import GeminiImageAdapter
from src.infrastructure.persistence.scheduled_task_repository import (
    PostgresScheduledTaskRepository,
)
from src.infrastructure.persistence.store_style_repository import StoreStyleRepository
from src.infrastructure.scheduling.scheduler_instance import task_scheduler
from src.infrastructure.usage.repository import UsageRepository
from src.infrastructure.web.httpx_reference_image_fetch import HttpxReferenceImageFetch


async def _noop_web_emit(_event: dict) -> None:
    """Sink padrão do `WebChannel` até o composition root injetar um transporte SSE real.

    O canal web ainda conversa direto com o LangGraph Platform na maioria dos
    caminhos (ver design `unify-message-delivery-pipeline`); o registry precisa
    do adapter registrado mesmo assim para `send_message` / fail-fast.
    """
    return None


def build_dependencies(
    *,
    telegram_bot: object | None = None,
    whatsapp_instance: str | None = None,
    web_emit: Callable[[dict], Awaitable[None]] | None = None,
) -> None:
    """Popula o `ChannelRegistry` do processo webapp (REQ-002 chat-channel-port).

    Registra `WebChannel`, `TelegramChannel` e `WhatsAppChannel` antes do
    primeiro request. Args opcionais permitem injeção em testes; em produção
    o bot Telegram e a instance WhatsApp vêm do ambiente.
    """
    if telegram_bot is None:
        from telegram import Bot

        telegram_bot = Bot(
            token=os.environ.get("TELEGRAM_BOT_TOKEN", "unconfigured")
        )
    if whatsapp_instance is None:
        whatsapp_instance = os.environ.get("EVOLUTION_INSTANCE_NAME", "unconfigured")

    ChannelRegistry.register(WebChannel(emit=web_emit or _noop_web_emit))
    ChannelRegistry.register(TelegramChannel(bot=telegram_bot))
    ChannelRegistry.register(WhatsAppChannel(instance=whatsapp_instance))


def build_plan_and_create_image() -> PlanAndCreateImage:
    """Monta PlanAndCreateImage com Gemini + repositório de estilos no Store."""
    postgres_uri = os.getenv("POSTGRES_URI")
    usage_repository = (
        UsageRepository(postgres_uri) if postgres_uri else None
    )
    return PlanAndCreateImage(
        image_gen=GeminiImageAdapter(usage_repository=usage_repository),
        styles=StoreStyleRepository(get_store()),
    )


def build_reference_image_fetch() -> ReferenceImageFetchPort:
    """Monta o fetcher de imagem de referência por URL (httpx, com validação/SSRF)."""
    return HttpxReferenceImageFetch()


def build_generate_requirements_document(
    output_dir: str | Path,
) -> GenerateRequirementsDocument:
    """Monta GenerateRequirementsDocument com o sink de filesystem no diretório dado."""
    return GenerateRequirementsDocument(FilesystemDocumentSink(output_dir))


def build_get_next_feature_number(specify_dir: str | Path) -> GetNextFeatureNumber:
    """Monta GetNextFeatureNumber com o store de artefatos SDD no filesystem."""
    return GetNextFeatureNumber(FilesystemSddArtifactStore(specify_dir))


def build_create_document(writer: DocumentWriterPort | None = None) -> CreateDocument:
    """Monta CreateDocument com um writer de documento.

    Sem argumentos, usa o writer nativo de DOCX (python-docx) — preserva o
    contrato legado da tool `create_docx_document`. Tools de outros formatos
    (xlsx/pptx) passam seu próprio writer concreto (XlsxWriter/PptxWriter) por
    injeção. O destino/URL do writer vivem na infraestrutura; este wiring é o
    único ponto que escolhe o adapter concreto. A aplicação permanece agnóstica.

    A `url` retornada precisa ser absoluta para que o agente nunca precise
    inventar um domínio ao apresentá-la (ver `DOCUMENT_BASE_URL` em `.env.example`).
    Sem `DOCUMENT_BASE_URL` explícita, cai para `FRONTEND_ORIGIN` — a mesma env
    var já usada como fonte da verdade para CORS — e só então para o default de
    dev `http://localhost:3000`. `image_server.py:8080` não serve mais estas
    rotas desde `consolidate-http-routes-langgraph`; um default apontando pra lá
    gerava um link morto por padrão (achado em `fix-docx-download-404-file-serving`).
    """
    base_url = (
        os.getenv("DOCUMENT_BASE_URL")
        or os.getenv("FRONTEND_ORIGIN")
        or "http://localhost:3000"
    ).rstrip("/")
    return CreateDocument(writer=writer or DocxWriter(url_prefix=f"{base_url}/api/files"))


def _scheduled_task_repository() -> PostgresScheduledTaskRepository:
    """Adapter concreto do repositório de tarefas agendadas (mesmo do REST)."""
    return PostgresScheduledTaskRepository(os.environ["POSTGRES_URI"])


def build_create_scheduled_task() -> CreateScheduledTask:
    """Monta CreateScheduledTask com o repositório Postgres e o `task_scheduler` singleton.

    Mesmos adapters concretos que `scheduling_router.py` já usa inline para o
    endpoint REST — só que expostos aqui para que as tools do agente
    (`create_scheduled_task`) possam resolver a dependência sem duplicar o
    wiring. Persistência + agendamento: o use case persiste primeiro e agenda
    depois, então uma falha no scheduler ainda permite re-agendar do banco.
    """
    return CreateScheduledTask(
        repository=_scheduled_task_repository(),
        scheduler=task_scheduler,
    )


def build_list_scheduled_tasks() -> ListScheduledTasks:
    """Monta ListScheduledTasks com o repositório Postgres (sem scheduler — listagem não agenda).

    Mesma configuração do endpoint REST (`scheduling_router.py`), só que
    exposta via composition root para que `list_scheduled_tasks` (tool do
    agente) resolva a dependência no mesmo lugar que o REST.
    """
    return ListScheduledTasks(repository=_scheduled_task_repository())


def build_cancel_scheduled_task() -> CancelScheduledTask:
    """Monta CancelScheduledTask com o repositório Postgres e o `task_scheduler` singleton.

    Cancelamento precisa desagendar o trigger (`scheduler.unschedule`) além
    de remover a linha do banco — mesmo par `(repository, scheduler)` que o
    endpoint REST já usa inline, exposto aqui para a tool do agente.
    """
    return CancelScheduledTask(
        repository=_scheduled_task_repository(),
        scheduler=task_scheduler,
    )
