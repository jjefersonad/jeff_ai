"""Renderer de aprovação inline + estado de aprovação pendente do `telegram_gateway`.

Responsabilidades desta task (`telegram-tool-approval-task-approval-3`):

- Construir um `InlineKeyboardMarkup` do `python-telegram-bot` a partir de
  um `InterruptInfo` (`build_keyboard`) — pure function, sem I/O, fácil de
  testar de forma isolada.
- Enviar a mensagem com o teclado ao `chat_id` e registrar a aprovação
  pendente num dict em memória (`send_approval_keyboard`), sobrescrevendo
  qualquer aprovação pendente anterior para o mesmo `chat_id`
  (single-user allowlist — sem risco de clobbering entre usuários
  distintos).
- Manter um `PendingApproval` por `chat_id` com o `thread_id` da
  aprovação, `action_requests`, `review_configs`, e um flag
  `awaiting_edit_text` que a task de callback (`-task-callback-4`)
  consulta para distinguir "tô esperando um texto de edição" de
  "tô esperando um clique num botão".

Responsabilidades adicionadas em `telegram-tool-approval-task-callback-4`:

- Processar `CallbackQuery` (botão Aprovar/Editar/Rejeitar) chamando
  `agent_runner.resume(...)` e limpando o estado pendente
  (`handle_approval_callback`).
- Auxiliar o `make_message_handler` a interceptar a PRÓXIMA mensagem
  de texto após "Editar" e disparar um REJECT+message (`consume_edit_text_reply`).
- Tratar falhas de resume com a mesma notificação genérica + cleanup
  do REQ-005.

O estado fica em memória no processo do gateway (decisão de design:
Non-Goal "Persistir o estado de aprovação pendente em Postgres" — o
benefício de sobreviver a um restart é baixo pro allowlist de 1
usuário, e o pior caso de um restart com aprovação pendente é
igual ao status quo pré-fix).

REQs cobertas:
- REQ-002 do `telegram-tool-approval-spec` (teclado inline, 3 botões
  padrão, "Editar" some em lote, registro de pendência).
- REQ-003/REQ-004/REQ-005 do spec (callback handler, edit-text
  intercept, swallow de exceções + cleanup).
- Pré-condição de REQ-005: `send_approval_keyboard` e
  `handle_approval_callback` engolem exceções do `bot.send_message`
  (mesma defesa de `_notify_failure` em `authorization.py`) — o
  handler nunca propaga falha do canal.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Protocol

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackQueryHandler

from src.application.ports.agent_runner import AgentRunResult, InterruptInfo
from src.infrastructure.telegram import bot_client
from src.infrastructure.usage.user_key import telegram_user_key

logger = logging.getLogger(__name__)


# Mapa label → callback_data. Mantido como constante de módulo para
# garantir que o renderer e o callback handler (task `task-callback-4`)
# usem exatamente os mesmos identificadores. A separação label/ID é
# importante: o label é texto visível ao usuário (localizável), o ID
# é contrato interno estável.
_DECISION_LABELS: dict[str, str] = {
    "approve": "Aprovar",
    "edit": "Editar",
    "reject": "Rejeitar",
}

# Ordem fixa dos botões no teclado (esquerda → direita). A spec exige
# labels nessa ordem (REQ-002 cenário "approve+edit+reject").
_DECISION_ORDER: tuple[str, ...] = ("approve", "edit", "reject")


@dataclass
class PendingApproval:
    """Estado de uma aprovação aguardando decisão do usuário.

    Mantido em `_pending_approvals` (dict por `chat_id`) enquanto o
    usuário não responde. Removido pelo callback handler quando a
    decisão chega (task `telegram-tool-approval-task-callback-4`).

    Attributes:
        thread_id: Thread LangGraph pausada — usado para o resume.
        action_requests: `ActionRequest`s serializadas (dict) que
            precisam de decisão.
        review_configs: `ReviewConfig`s correspondentes (mesmo índice
            de `action_requests`).
        awaiting_edit_text: `True` se o usuário tocou em "Editar" e
            a próxima mensagem de texto do `chat_id` deve ser
            interpretada como o ajuste (REQ-004).
    """

    thread_id: str
    action_requests: tuple[dict, ...]
    review_configs: tuple[dict, ...]
    awaiting_edit_text: bool = field(default=False)


# Estado global do gateway: dict[str, PendingApproval] indexado por
# chat_id. Vazio por padrão; popula em `send_approval_keyboard` e é
# consumido pelo callback handler. Volátil (perde em restart do
# gateway — documentado como Risk no design).
_pending_approvals: dict[str, PendingApproval] = {}


def get_pending_approval(chat_id: str) -> PendingApproval | None:
    """Devolve a aprovação pendente para `chat_id`, ou `None`.

    API exposta para a task de callback (`task-callback-4`) consultar
    o estado. NÃO usada dentro deste módulo (acesso direto a
    `_pending_approvals`). Encapsular via função facilita mock/test e
    deixa a fronteira de mutação explícita (push/pop passam por
    `set_pending_approval` e `clear_pending_approval`).
    """
    return _pending_approvals.get(chat_id)


def set_pending_approval(chat_id: str, approval: PendingApproval) -> None:
    """Registra/substitui a aprovação pendente para `chat_id`.

    Substitui qualquer pendência anterior (single-user allowlist — sem
    risco de clobbering entre usuários).
    """
    _pending_approvals[chat_id] = approval


def clear_pending_approval(chat_id: str) -> None:
    """Remove a aprovação pendente para `chat_id`, se existir.

    Idempotente: `pop` com default `None` evita `KeyError` quando não
    há nada a limpar (cenário "callback de botão velho", documentado
    no design como Risk #4).
    """
    _pending_approvals.pop(chat_id, None)


def discard_edit_text_wait(chat_id: str) -> None:
    """Limpa `awaiting_edit_text` de uma pendência existente, sem removê-la.

    Helper exposto para o `commands.dispatch_command` chamar
    (task `telegram-tool-approval-task-callback-4`, REQ-004 cenário 2
    "Usuário toca em Editar e depois usa um slash command"): quando o
    usuário envia um slash command em vez de uma resposta em texto, a
    pendência NÃO é removida (outra decisão ainda pode chegar), mas o
    flag `awaiting_edit_text` é zerado para que a próxima mensagem
    de texto NÃO seja interpretada como REJECT+message (clean
    abandonment). Idempotente: se não houver pendência ou o flag já
    for `False`, é no-op.
    """
    pending = _pending_approvals.get(chat_id)
    if pending is None:
        return
    pending.awaiting_edit_text = False


def build_keyboard(interrupt: InterruptInfo) -> InlineKeyboardMarkup:
    """Constrói o `InlineKeyboardMarkup` para apresentar a aprovação ao usuário.

    Pure function: não faz I/O. Recebe um `InterruptInfo` e devolve o
    teclado. Lógica de decisão:

    - 1 `action_request` + `allowed_decisions` que inclui approve/edit/reject
      → 3 botões (Aprovar/Editar/Rejeitar). Caso real hoje
      (a skill `image-generation` impõe 1 imagem por aprovação).
    - 2+ `action_requests` → 2 botões (Aprovar/Rejeitar). "Editar"
      some porque edição item-a-item de lote não está no escopo
      (REQ-002 cenário "Múltiplos action_requests no mesmo interrupt"
      + decisão do Open Question #2 do design). Aplica-se
      lote-todo: a mesma decisão vale para todos os items.
    - `allowed_decisions` que NÃO contém approve/edit/reject completos
      → cai para o subconjunto presente na ordem padrão de
      `_DECISION_ORDER`, filtrando os ausentes. Defesa em profundidade:
      a fonte (`tier_config.py`) hoje sempre envia as 3, mas o port
      não deve confiar cego.

    Os `callback_data` strings são os IDs em `_DECISION_LABELS` (`"approve"`,
    `"edit"`, `"reject"`) — contrato com a task de callback
    (`task-callback-4`).
    """
    has_multiple = len(interrupt.action_requests) > 1
    allowed: set[str] = set()
    if interrupt.review_configs:
        allowed.update(
            str(d) for d in interrupt.review_configs[0].get("allowed_decisions", ())
        )
    decisions = [d for d in _DECISION_ORDER if d in allowed]
    if has_multiple:
        decisions = [d for d in decisions if d != "edit"]

    row = [
        InlineKeyboardButton(text=_DECISION_LABELS[d], callback_data=d)
        for d in decisions
    ]
    return InlineKeyboardMarkup(inline_keyboard=[row])


def _interrupt_description(interrupt: InterruptInfo) -> str:
    """Monta o texto descritivo da aprovação para a mensagem do Telegram.

    Cada `action_request` tem um campo `description` (string já
    capturada pelo `tier_config._interrupt_description_for` antes do
    interrupt disparar — ver Decision #3 do design). Em lote, lista
    numerada; em single, usa direto. Defensive: se `description`
    faltar, cai no `name` da tool como fallback.
    """
    lines: list[str] = []
    for idx, ar in enumerate(interrupt.action_requests, start=1):
        desc = ar.get("description") or ar.get("name") or "<ação sem descrição>"
        if len(interrupt.action_requests) > 1:
            lines.append(f"{idx}. {desc}")
        else:
            lines.append(desc)
    header = "Aguardando aprovação:"
    return f"{header}\n" + "\n".join(lines)


async def send_approval_keyboard(
    bot: object,
    chat_id: str,
    thread_id: str,
    interrupt: InterruptInfo,
) -> None:
    """Envia a mensagem com teclado de aprovação e registra a pendência.

    Etapas:
    1. Constrói o `InlineKeyboardMarkup` via `build_keyboard`.
    2. Registra `PendingApproval(thread_id, action_requests,
       review_configs)` em `_pending_approvals[chat_id]`,
       sobrescrevendo pendência anterior (single-user).
    3. Envia a mensagem via
       `bot_client.call_bot_api(bot.send_message(...))` (mesma rota
       usada por `_notify_failure` em `authorization.py`, garantindo
       resiliência de retry/timeout).
    4. Engole QUALQUER exceção (defesa em profundidade: o loop de
       polling do `python-telegram-bot` não pode morrer por causa de
       uma falha de envio do teclado). Loga para diagnóstico
       operacional.

    O `awaiting_edit_text` é inicializado como `False`; quem muda
    para `True` é o callback handler quando o usuário toca em
    "Editar" (task `task-callback-4`, REQ-004).
    """
    try:
        markup = build_keyboard(interrupt)
        set_pending_approval(
            chat_id,
            PendingApproval(
                thread_id=thread_id,
                action_requests=interrupt.action_requests,
                review_configs=interrupt.review_configs,
            ),
        )
        text = _interrupt_description(interrupt)
        result = await bot_client.call_bot_api(
            lambda: bot.send_message(  # type: ignore[attr-defined]
                chat_id=chat_id, text=text, reply_markup=markup
            )
        )
        if not result.get("success", False):
            logger.error(
                "Falha ao enviar teclado de aprovação ao chat_id=%s: %s",
                chat_id,
                result.get("error", "<sem detalhe>"),
            )
    except Exception:  # noqa: BLE001 — fronteira do canal
        logger.exception(
            "Falha ao enviar/processar aprovação para chat_id=%s "
            "(thread_id=%s); loop de polling continua.",
            chat_id,
            thread_id,
        )


# ===========================================================================
# Callback handler — `telegram-tool-approval-task-callback-4`
# ===========================================================================
#
# Esta seção implementa a resolução da aprovação via Telegram: o
# `CallbackQueryHandler` (Aprovar/Editar/Rejeitar) chama
# `agent_runner.resume(...)` e remove a pendência. O edit-text intercept
# no `make_message_handler` chama `consume_edit_text_reply(...)` quando
# a próxima mensagem de texto chega.
#
# O `handle_approval_callback` é a função que o
# `CallbackQueryHandler` do `python-telegram-bot` invoca; o
# `telegram_gateway` (task `task-gateway-5`) registra o handler via
# `make_callback_query_handler(...).` Aqui isolamos a função em vez de
# injetá-la via closure para que os testes possam chamá-la diretamente
# com fakes (`MagicMock` para o `CallbackQuery`), sem precisar montar
# um `Update`/`Application` inteira.


# Texto enviado ao usuário quando o resume falha (REQ-005). Idêntico
# ao `_CHANNEL_ERROR_MESSAGE` em `authorization.py` — mantido como
# constante local para que este módulo não dependa daquele (defesa
# em profundidade: a fronteira do canal é unitária em si mesma).
_CHANNEL_ERROR_MESSAGE = (
    "Ocorreu uma falha ao processar sua decisão. "
    "Tente novamente em alguns instantes."
)

# Texto enviado quando o usuário toca em "Editar". Curto e direto:
# pede o ajuste em texto livre (a próxima mensagem de texto, se não
# for slash command, será capturada como REJECT+message via design
# Decision #4).
_EDIT_PROMPT_MESSAGE = (
    "Certo — envie em texto livre o ajuste que você quer no design."
)


class _AgentRunnerPort(Protocol):
    """Tipo estrutural mínimo: usado para anotação e composição.

    `resume(...)` é a nova operação introduzida pela change
    `telegram-tool-approval`; `run(...)` não é usado diretamente
    aqui, mas o port expõe os dois (o mesmo objeto `LangGraphDirectAgentRunner`
    é passado para `handle_approval_callback` E para `make_message_handler`).
    """

    async def run(self, *args: Any, **kwargs: Any) -> AgentRunResult: ...
    async def resume(self, *args: Any, **kwargs: Any) -> AgentRunResult: ...


class _BotLike(Protocol):
    """Tipo estrutural mínimo: bot com `send_message` e `answer_callback_query`."""

    async def send_message(
        self, chat_id: Any, text: str, *args: Any, **kwargs: Any
    ) -> Any: ...
    async def answer_callback_query(
        self, callback_query_id: Any, *args: Any, **kwargs: Any
    ) -> Any: ...


async def _send_error_to_chat(bot: _BotLike, chat_id: str) -> None:
    """Envia `_CHANNEL_ERROR_MESSAGE` ao chat absorvendo falhas de envio.

    Mesmo padrão de `_notify_failure` em `authorization.py` —
    defesa em profundidade: o handler do canal NUNCA propaga falha de
    `bot.send_message` (o loop de polling do `python-telegram-bot`
    precisa continuar vivo).
    """
    try:
        result = await bot_client.call_bot_api(
            lambda: bot.send_message(chat_id=chat_id, text=_CHANNEL_ERROR_MESSAGE)  # type: ignore[attr-defined]
        )
    except Exception:  # noqa: BLE001 — fronteira do canal
        logger.exception(
            "Falha ao notificar chat_id=%s sobre erro do resume; "
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


async def _answer_callback_safely(callback_query: Any) -> None:
    """Chama `query.answer()` (ack do Telegram) absorvendo falhas.

    O cliente do Telegram mostra um "loading" até o `answer()` chegar;
    se o handler falhar antes, o cliente fica preso. Por isso o
    `answer()` é chamado PRIMEIRO, e qualquer exceção é engolida
    (defesa de fronteira do canal — nunca propaga).
    """
    try:
        await callback_query.answer()
    except Exception:  # noqa: BLE001 — fronteira do canal
        logger.exception(
            "Falha ao chamar query.answer() para callback_query_id=%s; "
            "loop de polling continua.",
            getattr(callback_query, "id", "?"),
        )


async def _do_resume_safely(
    agent_runner: _AgentRunnerPort,
    *,
    thread_id: str,
    decisions: tuple[dict, ...],
    user_key: str | None = None,
) -> AgentRunResult | None:
    """Chama `agent_runner.resume(...)` e engole exceções.

    Retorna o `AgentRunResult` em caso de sucesso ou `None` em falha
    (o caller decide a próxima ação — normalmente enviar a mensagem
    de erro ao chat). A exceção é logada com `thread_id`+decisions
    para diagnóstico operacional; nunca propaga (REQ-005: handler
    nunca derruba o polling).
    """
    try:
        return await agent_runner.resume(
            thread_id=thread_id,
            decisions=decisions,
            user_key=user_key,
            use_default_profile=True,
        )
    except Exception:  # noqa: BLE001 — fronteira do canal (REQ-005)
        logger.exception(
            "agent_runner.resume() levantou exceção para thread_id=%s "
            "(decisions=%r); notificando chat_id.",
            thread_id,
            list(decisions),
        )
        return None


def _is_authorized(chat_id: str, authorized_chat_id: str) -> bool:
    """Replica o predicado de allowlist de `authorization.is_authorized_chat`.

    Mantido local para que `handle_approval_callback` não dependa
    de `authorization` (fronteira do canal, evita ciclo de imports).
    Mesma semântica: comparação literal de strings; `chat_id` vazio
    é não autorizado.
    """
    if not chat_id:
        return False
    return chat_id == authorized_chat_id


async def handle_approval_callback(
    *,
    authorized_chat_id: str,
    agent_runner: _AgentRunnerPort,
    bot: _BotLike,
    callback_query: Any,
) -> None:
    """Process `CallbackQuery` from approval buttons (Aprovar/Editar/Rejeitar).

    Pipeline (em ordem):
    1. Extrai `chat_id` e `data` do `CallbackQuery`. Se o chat não
       for autorizado, dropa silenciosamente (apenas `query.answer()`
       para desbloquear o cliente — REQ-003 cenário "chat não
       autorizado").
    2. Se não houver pendência registrada para o `chat_id`, dropa
       silenciosamente pelo mesmo motivo (REQ-003 cenário "sem
       aprovação pendente" — botão velho, replay).
    3. Para `data == "approve"` ou `"reject"`: chama
       `agent_runner.resume(...)` com a decisão correspondente,
       `query.answer()`, e remove a pendência. Falha do resume →
       notifica o chat com `_CHANNEL_ERROR_MESSAGE` (REQ-005).
    4. Para `data == "edit"`: marca `awaiting_edit_text=True` na
       pendência, envia o `_EDIT_PROMPT_MESSAGE`, e `query.answer()`.
       Nenhum resume é chamado (o resume só vem na próxima mensagem
       de texto — REQ-004 + design Decision #4).
    5. Para `data` desconhecido: dropa silenciosamente (defesa
       contra callbacks de botões velhos que não sejam nossos).

    Garantia de fronteira: NENHUMA exceção (nem do `bot`, nem do
    `agent_runner.resume`) propaga para fora desta função. O loop
    de polling do `python-telegram-bot` recebe sempre uma coroutine
    que resolve normalmente.
    """
    chat_id_raw = getattr(
        getattr(callback_query, "effective_chat", None), "id", None
    )
    chat_id = str(chat_id_raw) if chat_id_raw is not None else ""
    data = getattr(callback_query, "data", "")

    # Defesa contra qualquer callback que não seja nosso (e.g. botões
    # adicionados por outros handlers no futuro).
    if data not in ("approve", "edit", "reject"):
        await _answer_callback_safely(callback_query)
        return

    # 1. allowlist (REQ-003 cenário "chat não autorizado").
    if not _is_authorized(chat_id, authorized_chat_id):
        await _answer_callback_safely(callback_query)
        return

    # 2. pendência registrada (REQ-003 cenário "sem aprovação
    # pendente" — botão velho).
    pending = get_pending_approval(chat_id)
    if pending is None:
        await _answer_callback_safely(callback_query)
        return

    # 4. Editar: marca flag, pede texto, NÃO resume ainda.
    if data == "edit":
        pending.awaiting_edit_text = True
        await _send_edit_prompt(bot, chat_id)
        await _answer_callback_safely(callback_query)
        return

    # 3. Approve/Reject: resume, ack, cleanup.
    decision: dict[str, Any] = {"type": data}
    await _answer_callback_safely(callback_query)
    thread_id = pending.thread_id
    result = await _do_resume_safely(
        agent_runner,
        thread_id=thread_id,
        decisions=(decision,),
        user_key=telegram_user_key(chat_id),
    )
    if result is None:
        # Falha do resume (REQ-005) — notifica e limpa a pendência
        # para o chat não ficar preso aguardando uma decisão que
        # já falhou.
        await _send_error_to_chat(bot, chat_id)
    clear_pending_approval(chat_id)
    from src.infrastructure.scheduling.complete_after_resume import (
        maybe_complete_scheduled_task_after_resume,
    )

    await maybe_complete_scheduled_task_after_resume(
        thread_id=thread_id,
        decision_type=data,
        result=result,
    )


async def _send_edit_prompt(bot: _BotLike, chat_id: str) -> None:
    """Envia o `_EDIT_PROMPT_MESSAGE` ao chat absorvendo falhas.

    Mesmo padrão de `send_approval_keyboard` — engole qualquer
    exceção do canal para que o loop de polling continue.
    """
    try:
        result = await bot_client.call_bot_api(
            lambda: bot.send_message(chat_id=chat_id, text=_EDIT_PROMPT_MESSAGE)  # type: ignore[attr-defined]
        )
        if not result.get("success", False):
            logger.error(
                "Falha ao enviar prompt de edição ao chat_id=%s: %s",
                chat_id,
                result.get("error", "<sem detalhe>"),
            )
    except Exception:  # noqa: BLE001 — fronteira do canal
        logger.exception(
            "Falha ao enviar prompt de edição ao chat_id=%s; "
            "loop de polling continua.",
            chat_id,
        )


async def consume_edit_text_reply(
    *,
    authorized_chat_id: str,
    agent_runner: _AgentRunnerPort,
    bot: _BotLike,
    chat_id: str,
    user_text: str,
) -> bool:
    """Consome a PRÓXIMA mensagem de texto após "Editar".

    Chamado pelo `make_message_handler` ANTES de iniciar o fluxo
    normal (`agent_runner.run`). Se `_pending_approvals[chat_id]`
    existir com `awaiting_edit_text=True`, esta função:

    1. Constrói `decisions=({"type": "reject", "message": user_text},)`
       (design Decision #4 — REJECT+message, não EditDecision real,
       reusando o comportamento já existente e testado do
       gate de imagem).
    2. Chama `agent_runner.resume(...)`. Em falha, notifica o chat
       com `_CHANNEL_ERROR_MESSAGE` (REQ-005).
    3. Remove a pendência em qualquer caso (sucesso OU falha).
    4. Retorna `True` (caller NÃO deve chamar `agent_runner.run`).

    Se NÃO houver pendência em `awaiting_edit_text`, retorna
    `False` (caller segue o fluxo normal).

    Esta função NÃO propaga exceções — mesma garantia do
    `handle_approval_callback`.
    """
    if not _is_authorized(chat_id, authorized_chat_id):
        return False
    pending = get_pending_approval(chat_id)
    if pending is None or not pending.awaiting_edit_text:
        return False

    # Limpa a flag imediatamente (defesa contra duplo-consumo se o
    # `resume` falhar — chat não fica preso em "aguardando edição"
    # depois de uma falha).
    pending.awaiting_edit_text = False
    thread_id = pending.thread_id

    decision: dict[str, Any] = {"type": "reject", "message": user_text}
    result = await _do_resume_safely(
        agent_runner,
        thread_id=thread_id,
        decisions=(decision,),
        user_key=telegram_user_key(chat_id),
    )
    if result is None:
        await _send_error_to_chat(bot, chat_id)
    clear_pending_approval(chat_id)
    from src.infrastructure.scheduling.complete_after_resume import (
        maybe_complete_scheduled_task_after_resume,
    )

    await maybe_complete_scheduled_task_after_resume(
        thread_id=thread_id,
        decision_type="reject",
        result=result,
    )
    return True


# ===========================================================================
# Callback handler factory — `telegram-tool-approval-task-gateway-5`
# ===========================================================================
#
# O `python-telegram-bot` v20+ chama o handler registrado em
# `application.add_handler(CallbackQueryHandler(...))` como uma coroutine
# `(update, context) -> None`. O `update` carrega o `CallbackQuery` em
# `update.callback_query` (e `effective_chat` em `update.effective_chat`
# para o caso de o callback ser do tipo inline). Esta fábrica fecha os
# três parâmetros do `handle_approval_callback` (allowlist, runner, bot)
# e devolve o callable pronto para o `Application.add_handler`.


def make_approval_callback_handler(
    *,
    authorized_chat_id: str,
    agent_runner: _AgentRunnerPort,
    bot: _BotLike,
) -> Callable[[Any, Any], Awaitable[None]]:
    """Constrói o callable registrado como `CallbackQueryHandler` no gateway.

    Espelha o padrão de `authorization.make_message_handler` e
    `commands.make_command_dispatcher`: o callable devolvido recebe
    `(update, context)` no formato do `python-telegram-bot` e devolve
    uma coroutine — `application.run_polling()` do `python-telegram-bot`
    v20+ suporta handlers `async def` nativamente.

    A extração de `callback_query` do `update` é tolerante: se o
    `update` não tiver `callback_query` (falsos positivos do polling),
    o handler apenas registra um warning e retorna sem erro — mesma
    defesa da fronteira do canal (nunca derruba o polling).

    O `handle_approval_callback` em si já implementa toda a lógica
    REQ-003/004/005 (allowlist, pendência, decisions, ack, swallow).
    Esta fábrica é só o adapter (update → callback_query) que
    `telegram_gateway.main()` precisa para fazer
    `application.add_handler(CallbackQueryHandler(factory(...)))`.
    """
    async def _handle(update: Any, context: Any) -> None:
        callback_query = getattr(update, "callback_query", None)
        if callback_query is None:
            logger.warning(
                "CallbackQueryHandler recebeu update sem callback_query "
                "(update_id=%s); ignorando.",
                getattr(update, "update_id", "?"),
            )
            return
        await handle_approval_callback(
            authorized_chat_id=authorized_chat_id,
            agent_runner=agent_runner,
            bot=bot,
            callback_query=callback_query,
        )

    return CallbackQueryHandler(_handle)
