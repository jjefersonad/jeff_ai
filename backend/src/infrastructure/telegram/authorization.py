"""Filtro de allowlist de `chat_id` + propagação de `thread_id` para o `telegram_gateway`.

Responsabilidades destas tasks (`integracao-telegram-task-channel-2`,
`-task-channel-3`, `-task-channel-4` e `-task-channel-5`):

- Expor `is_authorized_chat(chat_id, authorized_chat_id) -> bool`: predicado
  puro que compara o `chat_id` recebido com o `TELEGRAM_AUTHORIZED_CHAT_ID`
  configurado (REQ-002 do `telegram-channel-spec`).
- Expor `CHANNEL_INSTRUCTION`: a string injetada como prefixo do `prompt`
  para instruir o agente a entregar a resposta via tool
  `send_telegram_message` (REQ-003).
- Expor `make_message_handler(authorized_chat_id, agent_runner, bot)` que
  devolve um callable compatível com `Application.add_handler(MessageHandler,
  ...)` do `python-telegram-bot`. O callable:
    1. Extrai o `chat_id` do `Update`.
    2. Se o chat NÃO for autorizado, descarta o update (sem chamar
       `get_or_create_thread_id` nem invocar o agente — REQ-002).
    3. Se o chat for autorizado, resolve o `thread_id` via
       `get_or_create_thread_id(chat_id)` exatamente uma vez e o propaga
       como `thread_id` da chamada a `agent_runner.run(...)` (REQ-001).
    4. Constrói o `prompt` final prefixando o texto do usuário com a
       `CHANNEL_INSTRUCTION` (REQ-003) e invoca o runner.
    5. Captura o `AgentRunResult` e usa APENAS `status`/`error` — nunca
       lê campos de texto, que o DTO real nem carrega (REQ-003).
    6. Quando `agent_runner.run()` levanta exceção OU o
       `AgentRunResult.status` indica falha/timeout (REQ-005), envia uma
       mensagem de erro legível ao `chat_id` de origem via
       `bot_client.call_bot_api(bot.send_message(...))` — esta é a única
       situação em que o canal envia texto por conta própria; o sucesso
       fica a cargo do agente chamando `send_telegram_message`.

  A captura de exceções é em camadas: a falha do runner é absorvida
  antes do envio; a falha do envio também é absorvida (defesa em
  profundidade) para que NENHUMA exceção escape do handler — o loop de
  polling do `python-telegram-bot` tem que continuar vivo mesmo quando
  tudo dá errado.
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Protocol

from src.domain.scheduling import ToolScope
from src.infrastructure.telegram import approval, bot_client
from src.infrastructure.telegram.thread_repository import get_or_create_thread_id
from src.infrastructure.usage.user_key import telegram_user_key

logger = logging.getLogger(__name__)

# Texto enviado ao usuário quando o agente falha ou o runner levanta
# exceção. Legível, sem vazar `thread_id` interno nem stack trace.
# REQ-005: "mensagem de erro legível ao chat de origem".
_CHANNEL_ERROR_MESSAGE = (
    "Ocorreu uma falha ao processar sua mensagem. "
    "Tente novamente em alguns instantes."
)

# Instrução de canal injetada como prefixo do `prompt` (REQ-003).
# Cita as tools de entrega pelo nome. No Telegram o DTO do runner NÃO
# devolve texto ao canal — se o agente não chamar uma tool de envio, o
# usuário não recebe nada (mesmo com a imagem já gerada em outputs/).
CHANNEL_INSTRUCTION = (
    "[Canal Telegram] Esta é uma conversa do usuário via Telegram. "
    "A entrega ao usuário SÓ acontece via tools de envio — nunca em "
    "texto livre no reasoning, nunca via markdown com `/api/images/...` "
    "(isso não renderiza no Telegram).\n"
    "- Texto: chame `send_telegram_message` com o texto da resposta.\n"
    "- Imagem gerada (`create_image_from_prompt` / "
    "`image_design_subagent`): depois do sucesso, chame "
    "`send_telegram_photo` com o campo `path` retornado pela tool "
    "(filesystem local). NÃO use o campo `url`. Pode enviar um caption "
    "curto.\n"
    "- Documento Office: chame `send_telegram_document` com o `path` "
    "retornado.\n\n"
)


class _AgentRunnerPort(Protocol):
    """Tipo estrutural mínimo: usado para anotação e composição.

    `run(...)` é definido em `agendamento-jeff-cli-task-application-1`
    (`AgentRunnerPort.run(thread_id, prompt, skills, tool_scope)`) como
    `async def`. O retorno é `AgentRunResult(thread_id, status, error)` —
    DTO sem campo de texto de resposta (ver `src/application/ports/
    agent_runner.py`). Esta task consome o retorno apenas para detectar
    falha (`status`/`error`); nunca para obter texto.
    """

    async def run(self, *args: Any, **kwargs: Any) -> Any: ...


class _BotLike(Protocol):
    """Tipo estrutural mínimo: bot do `python-telegram-bot` com `send_message`.

    O canal usa apenas `send_message(chat_id, text)` para notificar o
    usuário em caso de falha (REQ-005). Não é `telegram.Bot` em si —
    duck typing — para que o teste possa injetar um fake sem precisar
    de token real.
    """

    async def send_message(
        self, chat_id: Any, text: str, *args: Any, **kwargs: Any
    ) -> Any: ...


def is_authorized_chat(chat_id: str, authorized_chat_id: str) -> bool:
    """Devolve `True` se `chat_id` é o chat autorizado (allowlist de 1).

    Comparação literal de strings: o `TELEGRAM_AUTHORIZED_CHAT_ID` é
    configurado pelo operador e deve bater exatamente com o `chat_id` que
    o Telegram envia. `chat_id` vazio é tratado como nunca autorizado
    (defesa em profundidade contra updates malformados).
    """
    if not chat_id:
        return False
    return chat_id == authorized_chat_id


def build_channel_prompt(user_text: str) -> str:
    """Prefixa o texto do usuário com a instrução de canal (REQ-003).

    Mantida como função pura para que possa ser testada isoladamente e
    para deixar a montagem do prompt óbvia na leitura do `handler`. A
    instrução vem primeiro (lida pelo agente antes do pedido) e o texto
    original do usuário é preservado em seguida, separado por uma linha
    em branco para legibilidade no log do agente.
    """
    return f"{CHANNEL_INSTRUCTION}{user_text}"


def make_message_handler(
    *,
    authorized_chat_id: str,
    agent_runner: _AgentRunnerPort,
    bot: _BotLike,
) -> Callable[[Any, Any], Awaitable[None]]:
    """Constrói o handler de mensagens do gateway.

    Pipeline do callable, em ordem:
    1. allowlist de `chat_id` (REQ-002);
    2. resolução do `thread_id` (REQ-001);
    3. montagem do `prompt` com instrução de canal (REQ-003);
    4. invocação de `agent_runner.run(thread_id, prompt, skills, tool_scope)`;
    5. leitura **apenas** de `status`/`error` do `AgentRunResult` (REQ-003);
    6. em caso de falha (`status != "ok"`) ou exceção durante a
       invocação, envio de uma mensagem de erro legível ao `chat_id` de
       origem via `bot_client.call_bot_api(bot.send_message(...))` —
       REQ-005. A entrega normal (sucesso) é responsabilidade do
       agente chamando `send_telegram_message`.

    O callable devolvido recebe `(update, context)` no formato do
    `python-telegram-bot` e devolve uma coroutine — `application.run_polling()`
    do `python-telegram-bot` v20+ suporta handlers `async def` nativamente.

    Garantia de fronteira: NENHUMA exceção (nem do runner, nem do
    `bot.send_message`) se propaga para fora do handler. O loop de
    polling do `python-telegram-bot` recebe sempre uma coroutine que
    resolve normalmente — caso contrário uma única falha derruba o
    processo inteiro.
    """

    async def _notify_failure(chat_id: str) -> None:
        """Envia a mensagem de erro ao chat (REQ-005) absorvendo qualquer falha.

        Defesa em profundidade: mesmo se `bot.send_message` levantar
        (ex.: rede caiu também no momento do erro), o handler NÃO
        propaga. A falha é logada para diagnóstico e o loop de polling
        segue adiante.
        """
        try:
            result = await bot_client.call_bot_api(
                lambda: bot.send_message(chat_id=chat_id, text=_CHANNEL_ERROR_MESSAGE)
            )
        except Exception:  # noqa: BLE001 — fronteira do handler
            logger.exception(
                "Falha ao notificar chat_id=%s sobre erro do runner; "
                "loop de polling continua.",
                chat_id,
            )
            return
        if not result.get("success", False):
            logger.error(
                "Notificação de erro ao chat_id=%s falhou: %s",
                chat_id,
                result.get("error", "<sem detalhe>"),
            )

    async def handler(update: Any, context: Any) -> None:
        chat_id = str(update.effective_chat.id) if update.effective_chat else ""
        if not is_authorized_chat(chat_id, authorized_chat_id):
            return

        # REQ-004 do `telegram-tool-approval-spec`: se o chat está
        # aguardando texto de edição (usuário tocou em "Editar" no
        # teclado de aprovação), a PRÓXIMA mensagem de texto do
        # `chat_id` (não-slash) é interceptada ANTES do `agent_runner.run`
        # normal e transformada em um resume REJECT+message (design
        # Decision #4). O intercept roda aqui, no topo, antes da
        # resolução do `thread_id` e do `prompt` — para garantir que
        # o texto do usuário não vire um turno novo do agente.
        user_text = getattr(update.message, "text", "")
        intercepted = await approval.consume_edit_text_reply(
            authorized_chat_id=authorized_chat_id,
            agent_runner=agent_runner,
            bot=bot,
            chat_id=chat_id,
            user_text=user_text,
        )
        if intercepted:
            return

        # REQ-001: resolve o `thread_id` exatamente uma vez e o propaga para
        # a chamada ao `AgentRunnerPort`.
        thread_id = get_or_create_thread_id(chat_id)
        # track-user-token-usage REQ-002: identidade estável do canal
        # Telegram — `telegram:<chat_id>` no configurable do run.
        user_key = telegram_user_key(chat_id)
        # REQ-003: o prompt enviado ao agente inclui a instrução de canal
        # (cite `send_telegram_message` para forçar a entrega via tool) +
        # o texto original do usuário.
        prompt = build_channel_prompt(user_text)
        try:
            result = await agent_runner.run(
                thread_id=thread_id,
                prompt=prompt,
                skills=(),
                tool_scope=ToolScope.RESTRICTED,
                user_key=user_key,
            )
        except Exception:  # noqa: BLE001 — fronteira do handler (REQ-005)
            # `agent_runner.run()` propagou (caso atípico — o adapter
            # real engole, mas o port é um contrato, não uma promessa).
            # Logamos a falha com o `thread_id` para diagnóstico
            # operacional; para o usuário mandamos uma mensagem genérica
            # (não vaza `thread_id` nem stack trace). `logger.exception`
            # captura o traceback ativo automaticamente.
            logger.exception(
                "AgentRunnerPort.run() levantou exceção para thread_id=%s; "
                "notificando chat_id=%s.",
                thread_id,
                chat_id,
            )
            await _notify_failure(chat_id)
            return

        # REQ-003: usa APENAS `status`/`error` do `AgentRunResult` — o DTO
        # real (`thread_id`, `status`, `error`) não carrega texto de
        # resposta. A entrega da resposta em sucesso é responsabilidade
        # da tool `send_telegram_message`, chamada pelo próprio agente em
        # tool-call.
        status = getattr(result, "status", None)
        # REQ-002 do `telegram-tool-approval-spec`: status "interrupted"
        # é o caso do gate `interrupt_on` do LangGraph pausando o
        # grafo aguardando decisão humana (ex.: `create_image_from_prompt`
        # em `image_design_subagent`). Diferente de "error" — não é
        # falha, é o agente pedindo input. Ramo DEVE vir ANTES do
        # `if status != "ok"` abaixo (que trata "error"/"timeout" como
        # falha genérica).
        if status == "interrupted":
            interrupt = getattr(result, "interrupt", None)
            if interrupt is None:
                # Defesa em profundidade: se o adapter mandou "interrupted"
                # sem `interrupt`, trata como falha — não há como renderizar
                # aprovação.
                logger.error(
                    "AgentRunnerPort.run() retornou status='interrupted' sem "
                    "campo `interrupt` (thread_id=%s); notificando chat_id=%s.",
                    thread_id,
                    chat_id,
                )
                await _notify_failure(chat_id)
                return
            await approval.send_approval_keyboard(
                bot=bot,
                chat_id=chat_id,
                thread_id=thread_id,
                interrupt=interrupt,
            )
            return
        if status != "ok":
            # REQ-005: status != "ok" (inclui "error", "timeout" e
            # qualquer string livre usada pelo adapter) → notifica o
            # chat. O `error` do DTO é logado mas NÃO incluído no texto
            # enviado ao usuário (mensagens internas do agent runtime
            # podem vazar paths, URLs internas, etc.).
            logger.error(
                "AgentRunnerPort.run() retornou status=%r para thread_id=%s "
                "(error=%r); notificando chat_id=%s.",
                status,
                thread_id,
                getattr(result, "error", None),
                chat_id,
            )
            await _notify_failure(chat_id)

    return handler
