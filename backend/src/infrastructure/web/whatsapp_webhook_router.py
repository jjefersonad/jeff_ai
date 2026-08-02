"""`POST /api/webhooks/whatsapp` — recebe eventos da Evolution API.

Task `whatsapp-evolution-channel-task-channel-1`: monta a rota e delega o
payload bruto a `parse_inbound_message()`. `bootstrap_config()` é chamado a
cada requisição (não na importação do módulo) — o mesmo contrato fail-fast de
`telegram_gateway.bootstrap_config`, mas sem derrubar o processo do webapp
inteiro (que serve outras rotas independentes do WhatsApp) se a Evolution API
ainda não estiver configurada.

Task `whatsapp-evolution-channel-task-linking-3`: antes de qualquer
autorização, o texto da mensagem é testado como um código de vínculo
pendente via `RedeemWhatsAppLinkCode` (whatsapp-channel REQ-001). Código
válido cria o vínculo `phone_number -> user_id` e invalida o código;
`WhatsAppLinkCodeInvalidError` (código inexistente/expirado) é engolida
aqui mesmo — não é um erro, apenas o sinal de que o texto não era um
código, e o fluxo segue para a autorização normal (`task-channel-3`).

Task `whatsapp-evolution-channel-task-channel-3`: mensagens que não eram
código de vínculo só seguem adiante se `resolve_whatsapp_user_id()`
resolver o `phone_number` remetente a um `user_id` (REQ-003) — mesmo
padrão de fail-closed do Telegram (número sem vínculo é ignorado em
silêncio). Autorizado, obtém/cria o mapeamento `phone_number -> thread_id`
(REQ-002, `task-channel-2`). Não autorizado, nenhum mapeamento é
persistido.

Task `whatsapp-evolution-channel-task-channel-4`: mensagem autorizada é
roteada para o grafo `unified` via `route_authorized_message()`
(`AgentRunnerPort.run()`), com `user_key="whatsapp:<phone_number>"`
(REQ-005) — nenhum texto é lido nem enviado a partir do retorno (REQ-004).
O envio de resposta em si (caminho de sucesso) é feito pela tool
`send_whatsapp_message` (capability `whatsapp-tools`), chamada pelo agente.

Task `whatsapp-evolution-channel-task-channel-5`: se `route_authorized_message()`
levantar exceção OU o `AgentRunResult.status` devolvido indicar falha/timeout
(`status != "ok"`), `_notify_failure()` envia uma mensagem de erro legível
diretamente ao `phone_number` de origem via `evolution_client.send_text()`
(REQ-006) — a ÚNICA situação em que o canal envia texto por conta própria,
sem passar pela tool. Nenhuma exceção escapa do handler: a falha do runner é
absorvida antes do envio, e a falha do próprio `send_text` também é
absorvida (defesa em profundidade, mesmo padrão de
`telegram/authorization._notify_failure`).
"""
from __future__ import annotations

import logging
import os

from fastapi import APIRouter, Depends, Request

from src.application.ports.agent_runner import AgentRunnerPort
from src.application.ports.user_integration_repository import (
    UserIntegrationRepositoryPort,
)
from src.application.ports.whatsapp_link_code_repository import (
    WhatsAppLinkCodeRepositoryPort,
)
from src.application.use_cases.redeem_whatsapp_link_code import (
    RedeemWhatsAppLinkCode,
    WhatsAppLinkCodeInvalidError,
)
from src.infrastructure.agent_runtime.langgraph_direct_runner import (
    LangGraphDirectAgentRunner,
)
from src.infrastructure.ownership.store import resolve_whatsapp_user_id
from src.infrastructure.persistence.user_integrations_repository import (
    PostgresUserIntegrationRepository,
)
from src.infrastructure.persistence.whatsapp_link_codes_repository import (
    PostgresWhatsAppLinkCodeRepository,
)
from src.infrastructure.usage.user_key import whatsapp_user_key
from src.infrastructure.whatsapp.authorization import route_authorized_message
from src.infrastructure.whatsapp.evolution_client import (
    EvolutionConfigError,
    bootstrap_config,
    parse_inbound_message,
    send_text,
)
from src.infrastructure.whatsapp.thread_repository import get_or_create_thread_id

logger = logging.getLogger(__name__)

router = APIRouter()

# Texto enviado ao número de origem quando o agente falha ou o runner
# levanta exceção. Legível, sem vazar `thread_id` interno nem stack trace —
# mesmo texto/raciocínio de `telegram/authorization._CHANNEL_ERROR_MESSAGE`
# (REQ-006).
_CHANNEL_ERROR_MESSAGE = (
    "Ocorreu uma falha ao processar sua mensagem. "
    "Tente novamente em alguns instantes."
)


def _whatsapp_link_code_repository() -> WhatsAppLinkCodeRepositoryPort:
    """Constrói o repositório de códigos de vínculo WhatsApp a partir de `POSTGRES_URI`."""
    return PostgresWhatsAppLinkCodeRepository(os.environ["POSTGRES_URI"])


def _user_integration_repository() -> UserIntegrationRepositoryPort:
    """Constrói o repositório de integrações a partir de `POSTGRES_URI`."""
    return PostgresUserIntegrationRepository(os.environ["POSTGRES_URI"])


def _agent_runner() -> AgentRunnerPort:
    """Constrói o `LangGraphDirectAgentRunner` a partir de `POSTGRES_URI`.

    Mesmo adapter reaproveitado por `telegram_gateway`/`jeff_cli` (ver
    `LangGraphDirectAgentRunner` docstring) — compila `build_unified()`
    contra o mesmo Postgres, sem duplicar a fábrica do grafo.
    """
    return LangGraphDirectAgentRunner(postgres_uri=os.environ["POSTGRES_URI"])


async def _notify_failure(instance: str, phone_number: str) -> None:
    """Envia a mensagem de erro a `phone_number` (REQ-006) absorvendo qualquer falha.

    Defesa em profundidade: mesmo se `send_text` levantar (ex.: rede caiu
    também no momento do erro), esta função NÃO propaga — apenas loga para
    diagnóstico.
    """
    try:
        await send_text(instance, phone_number, _CHANNEL_ERROR_MESSAGE)
    except Exception:  # noqa: BLE001 — fronteira do handler (REQ-006)
        logger.exception(
            "Falha ao notificar phone_number=%s sobre erro do runner.", phone_number
        )


@router.post("/api/webhooks/whatsapp", status_code=200)
async def whatsapp_webhook_endpoint(
    request: Request,
    link_codes: WhatsAppLinkCodeRepositoryPort = Depends(_whatsapp_link_code_repository),
    user_integrations: UserIntegrationRepositoryPort = Depends(_user_integration_repository),
    agent_runner: AgentRunnerPort = Depends(_agent_runner),
) -> dict[str, bool]:
    """Recebe o payload bruto de webhook da Evolution API e delega ao parser."""
    try:
        config = bootstrap_config()
    except EvolutionConfigError as exc:
        logger.error("%s", exc)
        return {"received": False}

    payload = await request.json()
    message = parse_inbound_message(payload)
    if message is None:
        return {"received": False}

    redeem_link_code = RedeemWhatsAppLinkCode(
        link_code_repository=link_codes, user_integration_repository=user_integrations
    )
    try:
        await redeem_link_code.execute(code=message.text, phone_number=message.phone_number)
        logger.info("Vínculo WhatsApp criado para %s via código.", message.phone_number)
        return {"received": True}
    except WhatsAppLinkCodeInvalidError:
        pass  # não é um código de vínculo — segue para a autorização normal (task-channel-3)

    user_id = await resolve_whatsapp_user_id(message.phone_number)
    if user_id is None:
        logger.info("Mensagem WhatsApp de %s ignorada: sem vínculo ativo.", message.phone_number)
        return {"received": True}

    thread_id = get_or_create_thread_id(message.phone_number)
    logger.info(
        "Mensagem WhatsApp autorizada de %s (user_id=%s, thread_id=%s)",
        message.phone_number,
        user_id,
        thread_id,
    )
    try:
        result = await route_authorized_message(
            thread_id=thread_id,
            text=message.text,
            agent_runner=agent_runner,
            user_key=whatsapp_user_key(message.phone_number),
        )
    except Exception:  # noqa: BLE001 — fronteira do handler (REQ-006)
        logger.exception(
            "AgentRunnerPort.run() levantou exceção para thread_id=%s; notificando %s.",
            thread_id,
            message.phone_number,
        )
        await _notify_failure(config.instance_name, message.phone_number)
        return {"received": True}

    status = getattr(result, "status", None)
    if status != "ok":
        logger.error(
            "AgentRunnerPort.run() retornou status=%r para thread_id=%s (error=%r); "
            "notificando %s.",
            status,
            thread_id,
            getattr(result, "error", None),
            message.phone_number,
        )
        await _notify_failure(config.instance_name, message.phone_number)
    return {"received": True}
