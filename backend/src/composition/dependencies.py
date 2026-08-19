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

from src.application.ports.agent_profile_repository import (
    AgentProfileRepositoryPort,
)
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
from src.application.use_cases.archive_agent_profile import ArchiveAgentProfile
from src.application.use_cases.complete_scheduled_task_after_resume import (
    CompleteScheduledTaskAfterResume,
)
from src.application.use_cases.create_agent_profile import CreateAgentProfile
from src.application.use_cases.create_crm_contact import CreateCrmContact
from src.application.use_cases.create_crm_deal import CreateCrmDeal
from src.application.use_cases.create_crm_field_definition import (
    CreateCrmFieldDefinition,
)
from src.application.use_cases.create_crm_note import CreateCrmNote
from src.application.use_cases.get_agent_profile import GetAgentProfile
from src.application.use_cases.get_crm_deal import GetCrmDeal
from src.application.use_cases.list_agent_profiles import ListAgentProfiles
from src.application.use_cases.list_crm_contacts import ListCrmContacts
from src.application.use_cases.list_crm_deals import ListCrmDeals
from src.application.use_cases.list_crm_field_definitions import ListCrmFieldDefinitions
from src.application.use_cases.list_crm_notes import ListCrmNotes
from src.application.use_cases.move_crm_deal import MoveCrmDeal
from src.application.use_cases.resolve_delivery_target import ResolveDeliveryTarget
from src.application.use_cases.update_agent_profile import UpdateAgentProfile
from src.application.use_cases.update_crm_contact import UpdateCrmContact
from src.application.use_cases.update_crm_field_definition import (
    UpdateCrmFieldDefinition,
)
from src.composition.public_url import image_url_prefix
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
from src.infrastructure.persistence.agent_profile_repository import (
    PostgresAgentProfileRepository,
)
from src.infrastructure.persistence.crm_repository import PostgresCrmRepository
from src.infrastructure.persistence.scheduled_task_repository import (
    PostgresScheduledTaskRepository,
)
from src.infrastructure.persistence.store_style_repository import StoreStyleRepository
from src.infrastructure.persistence.user_integrations_repository import (
    PostgresUserIntegrationRepository,
)
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


def build_plan_and_create_image(
    *,
    output_dir: Path | None = None,
) -> PlanAndCreateImage:
    """Monta PlanAndCreateImage com Gemini + repositório de estilos no Store.

    `output_dir` tipicamente é `files/<user_id>/images/` (session-file-sandbox).
    """
    postgres_uri = os.getenv("POSTGRES_URI")
    usage_repository = (
        UsageRepository(postgres_uri) if postgres_uri else None
    )
    return PlanAndCreateImage(
        image_gen=GeminiImageAdapter(
            output_dir=output_dir,
            usage_repository=usage_repository,
            url_prefix=image_url_prefix(),
        ),
        styles=StoreStyleRepository(get_store()),
    )


def build_reference_image_fetch(
    *,
    output_dir: Path | None = None,
) -> ReferenceImageFetchPort:
    """Monta o fetcher de imagem de referência por URL (httpx, com validação/SSRF)."""
    return HttpxReferenceImageFetch(output_dir=output_dir)


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
    contrato legado de quem ainda monta `CreateDocument` direto. Tools
    canônicas de documento (docx/xlsx/pptx/pdf) usam o pipeline HTML
    (`RenderHtmlDocument` + converters); XlsxWriter/PptxWriter/DocxWriter
    permanecem para paths legados. O destino/URL do writer vivem na
    infraestrutura; a aplicação permanece agnóstica.

    A `url` retornada precisa ser absoluta para que o agente nunca precise
    inventar um domínio ao apresentá-la (ver `BASE_URL` em `.env.example`).
    Sem `BASE_URL` explícita, cai para `FRONTEND_ORIGIN` — a mesma env
    var já usada como fonte da verdade para CORS — e só então para o default de
    dev `http://localhost:3000`. `image_server.py:8080` não serve mais estas
    rotas desde `consolidate-http-routes-langgraph`; um default apontando pra lá
    gerava um link morto por padrão (achado em `fix-docx-download-404-file-serving`).
    """
    base_url = (
        os.getenv("BASE_URL")
        or os.getenv("FRONTEND_ORIGIN")
        or "http://localhost:3000"
    ).rstrip("/")
    return CreateDocument(writer=writer or DocxWriter(url_prefix=f"{base_url}/api/files"))


def _scheduled_task_repository() -> PostgresScheduledTaskRepository:
    """Adapter concreto do repositório de tarefas agendadas (mesmo do REST)."""
    return PostgresScheduledTaskRepository(os.environ["POSTGRES_URI"])


def _delivery_target_resolver() -> ResolveDeliveryTarget:
    """Resolver de destino de entrega (vínculos em `user_integrations`)."""
    return ResolveDeliveryTarget(
        repository=PostgresUserIntegrationRepository(os.environ["POSTGRES_URI"])
    )


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
        delivery_resolver=_delivery_target_resolver(),
        get_agent_profile=_get_agent_profile_use_case(),
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


def build_complete_scheduled_task_after_resume() -> CompleteScheduledTaskAfterResume:
    """Monta o hook pós-resume HITL para tarefas `WAITING_HUMAN`."""
    return CompleteScheduledTaskAfterResume(repository=_scheduled_task_repository())


def _crm_repository() -> PostgresCrmRepository:
    """Adapter concreto do repositório CRM (mesmo do REST)."""
    return PostgresCrmRepository(os.environ["POSTGRES_URI"])


def build_list_crm_contacts() -> ListCrmContacts:
    """Monta ListCrmContacts para as tools do agente."""
    return ListCrmContacts(repository=_crm_repository())


def build_create_crm_contact() -> CreateCrmContact:
    """Monta CreateCrmContact para as tools do agente."""
    return CreateCrmContact(repository=_crm_repository())


def build_update_crm_contact() -> UpdateCrmContact:
    """Monta UpdateCrmContact para as tools do agente."""
    return UpdateCrmContact(repository=_crm_repository())


def build_create_crm_note() -> CreateCrmNote:
    """Monta CreateCrmNote para as tools do agente."""
    return CreateCrmNote(repository=_crm_repository())


def build_list_crm_deals() -> ListCrmDeals:
    """Monta ListCrmDeals para as tools do agente."""
    return ListCrmDeals(repository=_crm_repository())


def build_create_crm_deal() -> CreateCrmDeal:
    """Monta CreateCrmDeal para as tools do agente."""
    return CreateCrmDeal(repository=_crm_repository())


def build_move_crm_deal() -> MoveCrmDeal:
    """Monta MoveCrmDeal para as tools do agente."""
    return MoveCrmDeal(repository=_crm_repository())


def build_get_crm_deal() -> GetCrmDeal:
    """Monta GetCrmDeal para as tools do agente (sales-pipeline-via-agent)."""
    return GetCrmDeal(repository=_crm_repository())


def build_list_crm_notes() -> ListCrmNotes:
    """Monta ListCrmNotes para as tools do agente (sales-pipeline-via-agent)."""
    return ListCrmNotes(repository=_crm_repository())


def build_create_crm_field_definition() -> CreateCrmFieldDefinition:
    """Monta CreateCrmFieldDefinition para API/tools."""
    return CreateCrmFieldDefinition(repository=_crm_repository())


def build_list_crm_field_definitions() -> ListCrmFieldDefinitions:
    """Monta ListCrmFieldDefinitions para API/tools."""
    return ListCrmFieldDefinitions(repository=_crm_repository())


def build_update_crm_field_definition() -> UpdateCrmFieldDefinition:
    """Monta UpdateCrmFieldDefinition para API/tools."""
    return UpdateCrmFieldDefinition(repository=_crm_repository())


def _agent_profile_repository() -> AgentProfileRepositoryPort:
    return PostgresAgentProfileRepository(os.environ["POSTGRES_URI"])


def _create_agent_profile_use_case() -> CreateAgentProfile:
    return CreateAgentProfile(repository=_agent_profile_repository())


def _update_agent_profile_use_case() -> UpdateAgentProfile:
    return UpdateAgentProfile(repository=_agent_profile_repository())


def _archive_agent_profile_use_case() -> ArchiveAgentProfile:
    return ArchiveAgentProfile(repository=_agent_profile_repository())


def _list_agent_profiles_use_case() -> ListAgentProfiles:
    return ListAgentProfiles(repository=_agent_profile_repository())


def _get_agent_profile_use_case() -> GetAgentProfile:
    return GetAgentProfile(repository=_agent_profile_repository())
