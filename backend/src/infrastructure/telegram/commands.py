"""Slash commands do canal Telegram (`/new`, `/title`, `/resume`, `/sessions`).

Responsabilidade desta task (`telegram-slash-commands-task-commands-1`):

- Parsear o texto de uma `Message` de slash command em `(nome, args)`.
- Despachar para um handler local por comando — nenhum deles invoca o
  agente; cada um responde diretamente ao chat via `bot.send_message`
  (REQ-001 do `telegram-slash-commands-spec`).
- Aplicar a allowlist de `chat_id` antes de despachar (REQ-006), reusando
  `authorization.is_authorized_chat` — mesma regra do `MessageHandler`.

`gateway-1` registra o callable devolvido por `make_command_dispatcher(...)`
no `CommandHandler` da `Application`, análogo a como
`authorization.make_message_handler` é registrado no `MessageHandler`.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Protocol

from src.infrastructure.telegram import approval, bot_client
from src.infrastructure.telegram.authorization import is_authorized_chat
from src.infrastructure.telegram.thread_repository import (
    create_thread_for_chat,
    get_or_create_thread_id,
    get_thread_by_title,
    list_threads_for_chat,
    set_active_thread,
    update_thread_title,
)

_NO_TITLE_LABEL = "<sem título>"
_NOT_FOUND_MESSAGE = "Thread não encontrada."


class _BotLike(Protocol):
    """Duck type mínimo: só `send_message`, igual ao de `authorization.py`.

    Definido localmente (em vez de importado) para manter `commands.py`
    desacoplado de `authorization.py` — a única dependência real entre os
    dois módulos é `is_authorized_chat`.
    """

    async def send_message(
        self, chat_id: Any, text: str, *args: Any, **kwargs: Any
    ) -> Any: ...


def _parse_command(text: str) -> tuple[str, str] | None:
    """Extrai `(nome, args)` de um texto de slash command, ou `None` se não for um.

    "/new pagamentos" -> ("new", "pagamentos"); "/sessions" -> ("sessions", "");
    "/resume abc-123" -> ("resume", "abc-123"). O nome vira minúsculo (o
    Telegram trata comandos como case-insensitive).
    """
    if not text.startswith("/"):
        return None
    body = text[1:]
    parts = body.split(maxsplit=1)
    if not parts:
        return None
    name = parts[0].lower()
    args = parts[1].strip() if len(parts) > 1 else ""
    return name, args


async def _send(bot: _BotLike, chat_id: str, text: str) -> None:
    """Responde ao chat via a mesma fronteira tipada de `authorization.py`."""
    await bot_client.call_bot_api(lambda: bot.send_message(chat_id=chat_id, text=text))


def _find_thread(chat_id: str, thread_id: str) -> dict[str, object] | None:
    """Resolve uma linha de `chat_id` por `thread_id`, ou `None` se não existir.

    Não há um `get_thread_by_id` dedicado no repositório — reusa
    `list_threads_for_chat`, cujo filtro por `chat_id` já garante que uma
    thread de outro chat nunca aparece (defesa contra enumeração no
    `/resume` por id — REQ-004).
    """
    for row in list_threads_for_chat(chat_id):
        if row["thread_id"] == thread_id:
            return row
    return None


async def handle_new(chat_id: str, args: str, bot: _BotLike) -> None:
    """Cria e ativa uma nova thread para `/new [título]` (REQ-002)."""
    title = args or None
    try:
        thread_id = create_thread_for_chat(chat_id, title)
    except ValueError:
        await _send(bot, chat_id, f'Título "{title}" já está em uso. Escolha outro.')
        return
    if title:
        await _send(bot, chat_id, f'Nova thread "{title}" criada (id {thread_id}).')
    else:
        await _send(bot, chat_id, f"Nova thread criada (id {thread_id}).")


async def handle_title(chat_id: str, args: str, bot: _BotLike) -> None:
    """Lê ou altera o título da thread ativa via `/title [título]` (REQ-003)."""
    thread_id = get_or_create_thread_id(chat_id)
    title = args
    if not title:
        current = _find_thread(chat_id, thread_id)
        current_title = current["title"] if current else None
        await _send(bot, chat_id, f"Título atual: {current_title or _NO_TITLE_LABEL}")
        return
    try:
        update_thread_title(thread_id, chat_id, title)
    except ValueError:
        await _send(
            bot, chat_id, f'Título "{title}" já está em uso por outra thread. Escolha outro.'
        )
        return
    await _send(bot, chat_id, f'Título atualizado para "{title}".')


async def handle_resume(chat_id: str, args: str, bot: _BotLike) -> None:
    """Troca a thread ativa via `/resume [id-ou-título]` (REQ-004)."""
    arg = args
    if not arg:
        thread_id = get_or_create_thread_id(chat_id)
        current = _find_thread(chat_id, thread_id)
        title = current["title"] if current else None
        await _send(bot, chat_id, f"Thread ativa: {thread_id} ({title or _NO_TITLE_LABEL})")
        return

    if "-" in arg:
        # Heurística: argumento com "-" parece um thread_id (UUID do
        # LangGraph). `_find_thread` só busca dentro de `chat_id` — uma
        # thread de outro chat nunca aparece, então a rejeição não vaza a
        # qual chat ela pertence (defesa contra enumeração).
        if _find_thread(chat_id, arg) is None:
            await _send(bot, chat_id, _NOT_FOUND_MESSAGE)
            return
        set_active_thread(chat_id, arg)
        await _send(bot, chat_id, f"Thread ativa alterada para {arg}.")
        return

    found = get_thread_by_title(chat_id, arg)
    if found is None:
        await _send(bot, chat_id, _NOT_FOUND_MESSAGE)
        return
    set_active_thread(chat_id, str(found["thread_id"]))
    await _send(bot, chat_id, f'Thread ativa alterada para "{arg}".')


async def handle_sessions(chat_id: str, args: str, bot: _BotLike) -> None:
    """Lista as threads do chat via `/sessions`, marcando a ativa (REQ-005)."""
    threads = list_threads_for_chat(chat_id)
    if not threads:
        await _send(bot, chat_id, "Nenhuma thread ainda; envie /new para começar.")
        return

    lines = [
        f"{'*' if t['active'] else ' '} {t['thread_id']} - {t['title'] or _NO_TITLE_LABEL}"
        for t in threads
    ]
    await _send(bot, chat_id, "\n".join(lines))


def make_command_dispatcher(
    *,
    authorized_chat_id: str,
    bot: _BotLike,
) -> Callable[[Any, Any], Awaitable[None]]:
    """Constrói o callback compatível com `Application.add_handler(CommandHandler(...))`.

    Espelha `authorization.make_message_handler`: a allowlist (REQ-006) e o
    `bot` ficam fechados no closure, para que `gateway-1` só precise passar
    o resultado ao `CommandHandler` junto da lista de comandos.
    """

    async def dispatch_command(update: Any, context: Any) -> None:
        chat_id = str(update.effective_chat.id) if update.effective_chat else ""
        text = getattr(update.message, "text", "") or ""
        parsed = _parse_command(text)
        if parsed is None:
            return
        if not is_authorized_chat(chat_id, authorized_chat_id):
            return

        # REQ-004 cenário 2 do `telegram-tool-approval-spec`: slash
        # commands durante `awaiting_edit_text` representam abandono
        # da edição — limpa o flag sem remover a pendência (a
        # decisão original ainda pode chegar via botão).
        approval.discard_edit_text_wait(chat_id=chat_id)

        name, args = parsed
        if name == "new":
            await handle_new(chat_id, args, bot)
        elif name == "title":
            await handle_title(chat_id, args, bot)
        elif name == "resume":
            await handle_resume(chat_id, args, bot)
        elif name == "sessions":
            await handle_sessions(chat_id, args, bot)

    return dispatch_command
