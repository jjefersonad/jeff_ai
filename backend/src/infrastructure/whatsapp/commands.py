"""Slash commands do canal WhatsApp (`/new`, `/title`, `/resume`, `/sessions`).

Responsabilidade desta task (`whatsapp-slash-commands-task-commands-1`):

- Parsear o texto de uma mensagem de slash command em `(nome, args)`.
- Despachar para um handler local por comando — nenhum deles invoca o
  agente; cada um responde diretamente ao `phone_number` via
  `evolution_client.send_text(instance, phone_number, text)` (REQ-001 do
  `whatsapp-slash-commands-spec`).
- A allowlist de `phone_number` (REQ-006) NÃO é responsabilidade deste
  módulo — ela é garantida pela ordem de chamada em
  `whatsapp_webhook_router.py` (próxima task, `channel-1`): este dispatcher
  só é invocado DEPOIS de `resolve_whatsapp_user_id`, garantindo que
  apenas números vinculados cheguem aqui.

Mesma forma estrutural de `src/infrastructure/telegram/commands.py`,
adaptado: `chat_id` → `phone_number`, `bot.send_message` (via closure) →
`evolution_client.send_text(instance, phone_number, text)` direto (já
`async def`, sem wrapper de fronteira — mesmo padrão de `_notify_failure`
em `whatsapp_webhook_router.py`). Sem equivalente ao `approval` do
Telegram: o WhatsApp não tem fluxo de aprovação/edit-text.
"""
from __future__ import annotations

from .evolution_client import send_text
from .thread_repository import (
    create_thread_for_number,
    get_or_create_thread_id,
    get_thread_by_title,
    list_threads_for_number,
    set_active_thread,
    update_thread_title,
)

_NOT_FOUND_MESSAGE = "Thread não encontrada."
_NO_TITLE_LABEL = "<sem título>"


def _parse_command(text: str) -> tuple[str, str] | None:
    """Extrai `(nome, args)` de um texto de slash command, ou `None` se não for um.

    "/new pagamentos" -> ("new", "pagamentos"); "/sessions" -> ("sessions", "").
    O nome vira minúsculo — o Telegram é case-insensitive para comandos e o
    WhatsApp não tem convenção própria, então seguimos o mesmo padrão.
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


async def _send(instance: str, phone_number: str, text: str) -> None:
    """Responde ao `phone_number` via `evolution_client.send_text` (async, propaga erros)."""
    await send_text(instance, phone_number, text)


def _find_thread(phone_number: str, thread_id: str) -> dict[str, object] | None:
    """Resolve uma linha de `phone_number` por `thread_id`, ou `None` se não existir.

    Não há um `get_thread_by_id` dedicado no repositório — reusa
    `list_threads_for_number`, cujo filtro por `phone_number` já garante que
    uma thread de outro número nunca aparece (defesa contra enumeração no
    `/resume` por id — REQ-004 do `whatsapp-slash-commands-spec`).
    """
    for row in list_threads_for_number(phone_number):
        if row["thread_id"] == thread_id:
            return row
    return None


async def handle_new(phone_number: str, args: str, instance: str) -> None:
    """Cria e ativa uma nova thread para `/new [título]` (REQ-002)."""
    title = args or None
    try:
        thread_id = create_thread_for_number(phone_number, title)
    except ValueError:
        await _send(instance, phone_number, f'Título "{title}" já está em uso. Escolha outro.')
        return
    if title:
        await _send(instance, phone_number, f'Nova thread "{title}" criada (id {thread_id}).')
    else:
        await _send(instance, phone_number, f"Nova thread criada (id {thread_id}).")


async def handle_title(phone_number: str, args: str, instance: str) -> None:
    """Lê ou altera o título da thread ativa via `/title [título]` (REQ-003)."""
    thread_id = get_or_create_thread_id(phone_number)
    title = args
    if not title:
        current = _find_thread(phone_number, thread_id)
        current_title = current["title"] if current else None
        await _send(instance, phone_number, f"Título atual: {current_title or _NO_TITLE_LABEL}")
        return
    try:
        update_thread_title(thread_id, phone_number, title)
    except ValueError:
        await _send(
            instance, phone_number, f'Título "{title}" já está em uso por outra thread. Escolha outro.'
        )
        return
    await _send(instance, phone_number, f'Título atualizado para "{title}".')


async def handle_resume(phone_number: str, args: str, instance: str) -> None:
    """Troca a thread ativa via `/resume [id-ou-título]` (REQ-004)."""
    arg = args
    if not arg:
        thread_id = get_or_create_thread_id(phone_number)
        current = _find_thread(phone_number, thread_id)
        title = current["title"] if current else None
        await _send(instance, phone_number, f"Thread ativa: {thread_id} ({title or _NO_TITLE_LABEL})")
        return

    if "-" in arg:
        # Heurística: argumento com "-" parece um `thread_id` (UUID do
        # LangGraph). `_find_thread` só busca dentro de `phone_number` —
        # uma thread de outro número nunca aparece, então a rejeição não
        # vaza a qual número ela pertence (defesa contra enumeração).
        if _find_thread(phone_number, arg) is None:
            await _send(instance, phone_number, _NOT_FOUND_MESSAGE)
            return
        set_active_thread(phone_number, arg)
        await _send(instance, phone_number, f"Thread ativa alterada para {arg}.")
        return

    found = get_thread_by_title(phone_number, arg)
    if found is None:
        await _send(instance, phone_number, _NOT_FOUND_MESSAGE)
        return
    set_active_thread(phone_number, str(found["thread_id"]))
    await _send(instance, phone_number, f'Thread ativa alterada para "{arg}".')


async def handle_sessions(phone_number: str, args: str, instance: str) -> None:
    """Lista as threads do número via `/sessions`, marcando a ativa (REQ-005)."""
    threads = list_threads_for_number(phone_number)
    if not threads:
        await _send(instance, phone_number, "Nenhuma thread ainda; envie /new para começar.")
        return

    lines = [
        f"{'*' if t['active'] else ' '} {t['thread_id']} - {t['title'] or _NO_TITLE_LABEL}"
        for t in threads
    ]
    await _send(instance, phone_number, "\n".join(lines))


async def dispatch_command(text: str, phone_number: str, instance: str) -> bool:
    """Parseia `text`; se for slash command reconhecido, despacha e retorna `True`.

    Devolve `False` sem efeito colateral para texto que não começa com `/` —
    sinal para `whatsapp_webhook_router.py` seguir com o roteamento normal
    para o agente (`AgentRunnerPort.run()`).
    """
    parsed = _parse_command(text)
    if parsed is None:
        return False

    name, args = parsed
    if name == "new":
        await handle_new(phone_number, args, instance)
    elif name == "title":
        await handle_title(phone_number, args, instance)
    elif name == "resume":
        await handle_resume(phone_number, args, instance)
    elif name == "sessions":
        await handle_sessions(phone_number, args, instance)
    else:
        # Comando `/foo` não reconhecido: comportamento similar a texto
        # normal — não é responsabilidade do dispatcher; deixa o router
        # rotear ao agente (que pode até estar preparado para explicar
        # comandos não suportados).
        return False

    return True
