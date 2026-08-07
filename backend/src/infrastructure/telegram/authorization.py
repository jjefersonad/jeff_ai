"""Filtro de allowlist de `chat_id` + propagação de `thread_id` para o `telegram_gateway`.

Responsabilidades:

- Expor `is_authorized_chat(chat_id, authorized_chat_id) -> bool`: predicado
  puro que compara o `chat_id` recebido com o `TELEGRAM_AUTHORIZED_CHAT_ID`
  configurado (REQ-002 do `telegram-channel-spec`).
- Expor `build_channel_prompt(user_text)` que devolve `user_text` sem
  pre-prefix (REQ-013) — a instrução de entrega vive no `_SYSTEM_PROMPT`.
- Expor `make_message_handler(authorized_chat_id, agent_runner, bot)` que
  devolve um callable compatível com `Application.add_handler(MessageHandler,
  ...)` do `python-telegram-bot`. O callable:
    1. Extrai o `chat_id` do `Update`.
    2. Se o chat NÃO for autorizado, descarta o update (sem chamar
       `get_or_create_thread_id` nem o caso de uso — REQ-002).
    3. Se o chat estiver aguardando texto de edição de aprovação, intercepta
       via `approval.consume_edit_text_reply` (REQ-004 telegram-tool-approval).
    4. Se autorizado, resolve `thread_id` via `get_or_create_thread_id(chat_id)`
       e chama `HandleChatMessage.execute(channel=TelegramChannel(bot=...),
       user_key=telegram_user_key(chat_id), thread_id=..., text=user_text)`
       — REQ-012 (`unify-message-delivery-pipeline`). O agent_runner NÃO é
       invocado diretamente daqui; falha, interrupt e entrega normal ficam
       a cargo do caso de uso + `TelegramChannel.deliver`.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Protocol

from src.application.use_cases.handle_chat_message import HandleChatMessage
from src.infrastructure.channels.telegram_channel import TelegramChannel
from src.infrastructure.ownership.store import resolve_telegram_user_id
from src.infrastructure.telegram import approval
from src.infrastructure.telegram.thread_repository import get_or_create_thread_id
from src.infrastructure.usage.user_key import telegram_user_key


class _AgentRunnerPort(Protocol):
    """Tipo estrutural mínimo: usado para anotação e composição.

    Injetado em `HandleChatMessage` e em `approval.consume_edit_text_reply`.
    O handler desta camada não chama `run(...)` diretamente (REQ-012).
    """

    async def run(self, *args: Any, **kwargs: Any) -> Any: ...


class _BotLike(Protocol):
    """Tipo estrutural mínimo: bot do `python-telegram-bot`.

    Injetado no `TelegramChannel` construído pelo handler. Duck typing
    para que o teste possa injetar um fake sem precisar de token real.
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


async def resolve_authorization(
    chat_id: str, authorized_chat_id: str
) -> tuple[bool, str | None]:
    """REQ-002 (delta `telegram-channel`, change `user-integration-credentials`).

    Autoriza `chat_id` por dois caminhos: (1) legado — igual ao
    `TELEGRAM_AUTHORIZED_CHAT_ID` configurado, mantido como fallback durante
    a janela de migração (design Migration Plan passo 3); (2) vínculo real —
    resolvido via `resolve_telegram_user_id` (`ownership/store.py`, mesmo
    resolvedor canônico usado por `resolve_user_id()` fora do contexto de um
    run). O caminho legado é checado primeiro (comparação de string, sem
    tocar o Postgres) — só cai para o vínculo real quando `chat_id` não bate
    com o allowlist. Devolve `(autorizado, user_id)`; `user_id` só vem
    preenchido no caminho de vínculo real (o legado não tem `user_id` a
    devolver, mesmo comportamento "zero servidores" de hoje).
    """
    if not chat_id:
        return False, None
    if chat_id == authorized_chat_id:
        return True, None
    user_id = await resolve_telegram_user_id(chat_id)
    if user_id is not None:
        return True, user_id
    return False, None


def build_channel_prompt(user_text: str) -> str:
    """Devolve `user_text` sem pre-prefix (REQ-013).

    A instrução de entrega moveu-se para a seção "Entrega de mensagens"
    do `_SYSTEM_PROMPT` do agente — o prompt do usuário fica só o texto.
    """
    return user_text


def make_message_handler(
    *,
    authorized_chat_id: str,
    agent_runner: _AgentRunnerPort,
    bot: _BotLike,
) -> Callable[[Any, Any], Awaitable[None]]:
    """Constrói o handler de mensagens do gateway.

    Pipeline do callable, em ordem:
    1. allowlist de `chat_id` (REQ-002);
    2. intercept de texto de edição de aprovação (REQ-004 tool-approval);
    3. resolução do `thread_id` (REQ-001);
    4. `HandleChatMessage.execute(...)` com `TelegramChannel` (REQ-012).

    O callable devolvido recebe `(update, context)` no formato do
    `python-telegram-bot` e devolve uma coroutine. Exceções do agente são
    engolidas pelo caso de uso — o loop de polling continua vivo.
    """

    async def handler(update: Any, context: Any) -> None:
        chat_id = str(update.effective_chat.id) if update.effective_chat else ""
        authorized, _linked_user_id = await resolve_authorization(
            chat_id, authorized_chat_id
        )
        if not authorized:
            return

        # REQ-004 do `telegram-tool-approval-spec`: se o chat está
        # aguardando texto de edição (usuário tocou em "Editar"), a
        # PRÓXIMA mensagem de texto do `chat_id` (não-slash) é
        # interceptada ANTES do fluxo normal.
        user_text = getattr(update.message, "text", "") or ""
        intercepted = await approval.consume_edit_text_reply(
            authorized_chat_id=authorized_chat_id,
            agent_runner=agent_runner,
            bot=bot,
            chat_id=chat_id,
            user_text=user_text,
        )
        if intercepted:
            return

        thread_id = get_or_create_thread_id(chat_id)
        user_key = telegram_user_key(chat_id)
        use_case = HandleChatMessage(agent_runner=agent_runner)
        await use_case.execute(
            channel=TelegramChannel(bot=bot),
            user_key=user_key,
            thread_id=thread_id,
            text=user_text,
        )

    return handler
