"""Estado de aprovação pendente do canal WhatsApp + resolução via webhook.

Mirror de `src/infrastructure/telegram/approval.py`'s `_pending_approvals`
(change `whatsapp-tool-approval`, design Decision 2), indexado por
`phone_number` em vez de `chat_id`. Estado em memória no processo do
webapp — mesmo trade-off aceito para o Telegram (Non-Goal: persistir em
Postgres; o benefício de sobreviver a um restart é baixo pro volume de
uso atual, e o pior caso — um restart com aprovação pendente — é igual
ao status quo pré-fix).

`task-foundation-1` cobre o estado (`PendingApproval` + register/get/clear).
O envio da mensagem de aprovação (botões nativos ou menu em texto) é
`WhatsAppChannel._send_interruption_prompt` (`task-delivery-2a`).

`task-webhook-3`: `match_decision_text`/`handle_pending_approval_reply` resolvem
approve/reject a partir do texto recebido pelo webhook — botão-tap e
resposta numérica chegam pelo MESMO campo `text` (confirmado no spike
`task-spike-1`: a Evolution API não expõe um payload de botão distinto para
este fork/versão).

`task-webhook-4` (esta seção): fluxo "Ajustar" (REQ-010). Ao reconhecer
"Ajustar"/"3", `handle_pending_approval_reply` NÃO resume ainda — marca
`awaiting_edit_text=True` na pendência e envia um prompt pedindo o texto do
ajuste (`evolution_client.send_text`, por isso a função ganhou o parâmetro
`instance`). A PRÓXIMA mensagem de texto desse `phone_number` (qualquer
texto, sem passar por `match_decision_text`) é consumida como o ajuste e
vira `resume={"decisions": [{"type": "reject", "message": <texto>}]}` —
mesma semântica de `telegram-tool-approval` REQ-004: "Ajustar" é
implementado como um REJECT com feedback, reaproveitando o replanejamento
que o subagente já sabe fazer, não como merge real de argumentos.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from src.infrastructure.usage.user_key import whatsapp_user_key
from src.infrastructure.whatsapp import evolution_client


@dataclass
class PendingApproval:
    """Estado de uma aprovação aguardando decisão do usuário via WhatsApp.

    Attributes:
        thread_id: Thread LangGraph pausada — usado para o resume.
        action_requests: `ActionRequest`s serializadas (dict) que precisam
            de decisão.
        review_configs: `ReviewConfig`s correspondentes (mesmo índice de
            `action_requests`).
        awaiting_edit_text: `True` se o usuário escolheu "Ajustar" e a
            próxima mensagem de texto do `phone_number` deve ser
            interpretada como o ajuste (REQ-010).
    """

    thread_id: str
    action_requests: tuple[dict, ...]
    review_configs: tuple[dict, ...]
    awaiting_edit_text: bool = field(default=False)


# Estado global do webapp: dict[str, PendingApproval] indexado por
# phone_number. Volátil (perde em restart — documentado como Risk no
# design).
_pending_approvals: dict[str, PendingApproval] = {}


def get_pending_approval(phone_number: str) -> PendingApproval | None:
    """Devolve a aprovação pendente para `phone_number`, ou `None`."""
    return _pending_approvals.get(phone_number)


def set_pending_approval(phone_number: str, approval: PendingApproval) -> None:
    """Registra/substitui a aprovação pendente para `phone_number`."""
    _pending_approvals[phone_number] = approval


def clear_pending_approval(phone_number: str) -> None:
    """Remove a aprovação pendente para `phone_number`, se existir.

    Idempotente: `pop` com default `None` evita `KeyError` quando não há
    nada a limpar (cenário "resposta de aprovação já resolvida ou
    expirada", REQ-011).
    """
    _pending_approvals.pop(phone_number, None)


# Texto reconhecido (normalizado: strip + lower) → decisão. "aprovar"/"1" e
# "rejeitar"/"2" cobrem tanto o botão-tap (texto = label do botão) quanto o
# menu numerado de fallback. "ajustar"/"3" NÃO resulta em resume direto —
# `handle_pending_approval_reply` trata "adjust" como um caso especial
# (marca awaiting_edit_text em vez de resumir imediatamente).
_TEXT_TO_DECISION: dict[str, str] = {
    "aprovar": "approve",
    "1": "approve",
    "rejeitar": "reject",
    "2": "reject",
    "ajustar": "adjust",
    "3": "adjust",
}

_ADJUST_PROMPT_MESSAGE = (
    "Certo — envie em texto livre o ajuste que você quer."
)


def match_decision_text(text: str) -> str | None:
    """Resolve um texto de resposta (botão-tap ou menu numerado) para uma decisão.

    Normaliza (`strip` + `lower`) antes de comparar. Devolve `"approve"`,
    `"reject"`, `"adjust"`, ou `None` se o texto não corresponder a
    nenhuma opção reconhecida.
    """
    return _TEXT_TO_DECISION.get(text.strip().lower())


class _AgentRunnerPort(Protocol):
    """Tipo estrutural mínimo — mesmo papel do `_AgentRunnerPort` em `telegram/approval.py`."""

    async def resume(self, *args: Any, **kwargs: Any) -> Any: ...


async def handle_pending_approval_reply(
    *,
    phone_number: str,
    text: str,
    instance: str,
    agent_runner: _AgentRunnerPort,
) -> bool:
    """Intercepta uma resposta de aprovação pendente do WhatsApp (REQ-009/010/011).

    Chamado pelo webhook ANTES do dispatch de slash command e ANTES do
    roteamento normal para `HandleChatMessage` (design Decision 3).

    Ordem de resolução:
    1. Sem pendência para `phone_number` → `False` (REQ-011, segue
       roteamento normal).
    2. Pendência com `awaiting_edit_text=True` → QUALQUER texto (sem
       passar por `match_decision_text`) é o ajuste: resume
       `{"type": "reject", "message": text}`, limpa a pendência, `True`.
    3. Texto não reconhecido por `match_decision_text` → `False` (REQ-011).
    4. `"adjust"` → marca `awaiting_edit_text=True`, envia o prompt
       pedindo o texto do ajuste, NÃO resume ainda, `True` (REQ-010).
    5. `"approve"`/`"reject"` → resume imediato, limpa a pendência,
       `True` (REQ-009).
    """
    pending = get_pending_approval(phone_number)
    if pending is None:
        return False

    if pending.awaiting_edit_text:
        clear_pending_approval(phone_number)
        await agent_runner.resume(
            thread_id=pending.thread_id,
            decisions=({"type": "reject", "message": text},),
            user_key=whatsapp_user_key(phone_number),
        )
        return True

    decision_type = match_decision_text(text)
    if decision_type is None:
        return False

    if decision_type == "adjust":
        pending.awaiting_edit_text = True
        await evolution_client.send_text(instance, phone_number, _ADJUST_PROMPT_MESSAGE)
        return True

    clear_pending_approval(phone_number)
    await agent_runner.resume(
        thread_id=pending.thread_id,
        decisions=({"type": decision_type},),
        user_key=whatsapp_user_key(phone_number),
    )
    return True


__all__ = [
    "PendingApproval",
    "get_pending_approval",
    "set_pending_approval",
    "clear_pending_approval",
    "match_decision_text",
    "handle_pending_approval_reply",
]
