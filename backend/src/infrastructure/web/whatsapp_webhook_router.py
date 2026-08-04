"""`POST /api/webhooks/whatsapp/{token}` — recebe eventos da Evolution API.

Task `whatsapp-evolution-channel-task-channel-1`: monta a rota e delega o
payload bruto a `parse_inbound_message()`. `bootstrap_config()` é chamado a
cada requisição (não na importação do módulo) — o mesmo contrato fail-fast de
`telegram_gateway.bootstrap_config`, mas sem derrubar o processo do webapp
inteiro (que serve outras rotas independentes do WhatsApp) se a Evolution API
ainda não estiver configurada.

Autenticação por token na URL (achado de teste manual pós-implementação,
fora do escopo original das tasks acima): o `require_auth` GLOBAL de
`webapp.py` rejeitaria toda chamada da Evolution API (sem cookie de sessão),
e mesmo liberando a rota, nada validava que o `phone_number` do payload
correspondia a uma chamada real da Evolution API — qualquer um poderia
forjar mensagens de um número já vinculado a um usuário. Fix: o path
carrega um token compartilhado (`EVOLUTION_WEBHOOK_TOKEN`), comparado em
tempo constante (`secrets.compare_digest`) logo após `bootstrap_config()`;
token incorreto retorna 404 (não 401/403, para não confirmar a existência
da rota a quem estiver adivinhando). `/api/webhooks/whatsapp/` foi
adicionada a `PUBLIC_PATHS` (`session_resolver._DEFAULT_PUBLIC_PATHS`) —
o token é o mecanismo de autenticação real desta rota, `require_auth`
(cookie de sessão de navegador) não se aplica a um chamador servidor-a-
servidor.

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

Task `unify-message-delivery-pipeline-task-whatsapp-1` (REQ-006): mensagem
autorizada (não slash) é roteada via `HandleChatMessage.execute(
channel=WhatsAppChannel(...), ...)` — o agent_runner NÃO é chamado
diretamente daqui. Falha/interrupt/entrega ficam a cargo do caso de uso +
`WhatsAppChannel.deliver`.

Task `whatsapp-slash-commands-task-channel-1`: após a autorização por vínculo
ativo e antes do roteamento para o agente, o webhook chama
`commands.dispatch_command(message.text, message.phone_number, config.instance_name)`.
Se retornar `True` (texto era um slash command reconhecido — `/new`, `/title`,
`/resume`, `/sessions`), o handler responde diretamente ao número via
`evolution_client.send_text` (já feito dentro do dispatcher) e retorna
imediatamente — `HandleChatMessage` NÃO é chamado. Para texto normal,
`dispatch_command` retorna `False` sem efeito colateral e o fluxo segue
inalterado. Mesma posição do split no Telegram (`filters.COMMAND`), só que
implementada manualmente dentro desta função por não haver um framework de
dispatch no webhook HTTP único do WhatsApp. REQ-006 do `whatsapp-slash-commands`
é garantida pela ordem: `resolve_whatsapp_user_id` acima deste bloco, então
nenhum dispatcher é alcançável para `phone_number` sem vínculo ativo.
"""
from __future__ import annotations

import logging
import os
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request

from src.application.ports.agent_runner import AgentRunnerPort
from src.application.ports.user_integration_repository import (
    UserIntegrationRepositoryPort,
)
from src.application.ports.whatsapp_link_code_repository import (
    WhatsAppLinkCodeRepositoryPort,
)
from src.application.use_cases.handle_chat_message import HandleChatMessage
from src.application.use_cases.redeem_whatsapp_link_code import (
    RedeemWhatsAppLinkCode,
    WhatsAppLinkCodeInvalidError,
)
from src.infrastructure.channels.whatsapp_channel import WhatsAppChannel
from src.infrastructure.ownership.store import resolve_whatsapp_user_id
from src.infrastructure.persistence.user_integrations_repository import (
    PostgresUserIntegrationRepository,
)
from src.infrastructure.persistence.whatsapp_link_codes_repository import (
    PostgresWhatsAppLinkCodeRepository,
)
from src.infrastructure.usage.user_key import whatsapp_user_key
from src.infrastructure.whatsapp import commands
from src.infrastructure.whatsapp.evolution_client import (
    EvolutionConfigError,
    bootstrap_config,
    parse_inbound_message,
    send_text,
)
from src.infrastructure.whatsapp.thread_repository import get_or_create_thread_id

logger = logging.getLogger(__name__)

router = APIRouter()

# Enviada ao número de origem após um código de vínculo válido ser redimido
# (achado 2026-08-04: o canal criava o vínculo mas nunca confirmava para o
# usuário — diferente do Telegram, que envia `start_command._SUCCESS_MESSAGE`
# no mesmo cenário). Mesmo texto/tom da mensagem de sucesso do Telegram.
_LINK_SUCCESS_MESSAGE = "Número vinculado com sucesso! Você já pode usar o Jeff AI por aqui."


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

    Import LAZY (dentro da função, não no topo do módulo): achado real
    (2026-08-03) — um import top-level aqui faz `webapp.py` (que importa
    este router para montar `/api/webhooks/whatsapp/{token}`) carregar
    `build_unified()` e toda a stack de MCP client já no boot do processo,
    derrubando TODO o app (imagens, documentos, auth, integrações) se algo
    nessa cadeia falhar — foi exatamente o que aconteceu (incompatibilidade
    de versão `mcp`/`langchain-mcp-adapters`, ver `Dockerfile.backend`).
    Mesmo raciocínio de `telegram_gateway.build_runner()`, só que ali o
    motivo original era startup rápido; aqui é isolamento de blast radius.
    """
    from src.infrastructure.agent_runtime.langgraph_direct_runner import (
        LangGraphDirectAgentRunner,
    )

    return LangGraphDirectAgentRunner(postgres_uri=os.environ["POSTGRES_URI"])


@router.post("/api/webhooks/whatsapp/{token}", status_code=200)
async def whatsapp_webhook_endpoint(
    token: str,
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

    if not secrets.compare_digest(token, config.webhook_token):
        # 404, não 401/403: não confirma a existência da rota a quem
        # estiver tentando adivinhar o token por tentativa e erro.
        raise HTTPException(status_code=404)

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
        try:
            await send_text(config.instance_name, message.phone_number, _LINK_SUCCESS_MESSAGE)
        except Exception:  # noqa: BLE001 — confirmação não pode derrubar o vínculo já criado
            logger.exception(
                "Vínculo criado para %s, mas falhou notificar a confirmação.",
                message.phone_number,
            )
        return {"received": True}
    except WhatsAppLinkCodeInvalidError:
        pass  # não é um código de vínculo — segue para a autorização normal (task-channel-3)

    user_id = await resolve_whatsapp_user_id(message.phone_number)
    if user_id is None:
        logger.info("Mensagem WhatsApp de %s ignorada: sem vínculo ativo.", message.phone_number)
        return {"received": True}

    # Task `whatsapp-slash-commands-task-channel-1`: o dispatcher de comandos
    # (`/new`, `/title`, `/resume`, `/sessions`) é chamado DEPOIS da
    # autorização por vínculo (acima) e ANTES do roteamento para o agente
    # (abaixo). Slash commands respondem diretamente via `evolution_client`
    # e NÃO invocam o agente — `dispatch_command` retorna `True` para
    # sinalizar que o webhook deve parar aqui. Para texto sem `/`, retorna
    # `False` e o fluxo segue normalmente (`commands.dispatch_command`
    # simplesmente não toca em nada nesse caminho).
    if await commands.dispatch_command(
        message.text, message.phone_number, config.instance_name
    ):
        logger.info(
            "Slash command WhatsApp despachado para %s (user_id=%s); agente NÃO chamado.",
            message.phone_number,
            user_id,
        )
        return {"received": True}

    thread_id = get_or_create_thread_id(message.phone_number)
    logger.info(
        "Mensagem WhatsApp autorizada de %s (user_id=%s, thread_id=%s)",
        message.phone_number,
        user_id,
        thread_id,
    )
    use_case = HandleChatMessage(agent_runner=agent_runner)
    await use_case.execute(
        channel=WhatsAppChannel(instance=config.instance_name),
        user_key=whatsapp_user_key(message.phone_number),
        thread_id=thread_id,
        text=message.text,
    )
    return {"received": True}
