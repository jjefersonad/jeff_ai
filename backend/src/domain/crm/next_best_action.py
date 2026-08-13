"""Geração de rascunho de follow-up (REQ-001, REQ-004, REQ-005 next-best-action-suggestion).

PURO: zero import de framework/repositório — `suggest` recebe as notas do
deal e `suggest_all` recebe os deals já resolvidos pelo chamador, não
consultam `crm_notes`/`crm_deals` sozinhos. Mesmo princípio de
`stagnation.is_stale`.

A pesquisa de slot de calendário (REQ-005) também é injetada: `suggest`
recebe um `slot_finder` chamável em vez de importar `scheduling_tools`
diretamente, mantendo o módulo livre de dependências de tool/framework
e permitindo que a change `agendamento-jeff-cli` (que vai expor
`find_free_slot`) seja plugada depois sem alterar este arquivo.
"""
from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any

from src.domain.crm.models import Deal, DealStage, Note
from src.domain.crm.stagnation import is_stale

_PROPOSAL_KEYWORD = re.compile(r"proposta", re.IGNORECASE)

_MAX_SUGGESTIONS = 10

# REQ-005: apenas `proposal` e `negotiation` recebem sugestão de slot
# de calendário. `qualified` ainda é cedo (proposta nem saiu);
# `won`/`lost` estão terminados.
_CALENDAR_SLOT_STAGES: frozenset[DealStage] = frozenset(
    {DealStage.PROPOSAL, DealStage.NEGOTIATION}
)

# Contrato do `slot_finder` injetado: devolve `dict | None` com chaves
# `start`/`end`/`calendar_link` quando há slot livre, ou `None` caso
# contrário. Esta abstração mantém `next_best_action` desacoplado de
# `scheduling_tools` (que pertence à change `agendamento-jeff-cli`).
SlotFinder = Callable[..., "dict[str, Any] | None"]


def suggest(
    notes: list[Note],
    *,
    now: datetime | None = None,
    deal_stage: DealStage | None = None,
    slot_finder: SlotFinder | None = None,
) -> dict[str, object]:
    """Gera `{kind, payload, editable_text, calendar_slot?}` citando só fatos de `notes`.

    Se alguma nota menciona "proposta", referencia a idade em dias da mais
    recente dessas notas (ex.: "há 3 dias"). Sem essa nota, o rascunho nunca
    afirma que uma proposta foi enviada — sugere confirmar interesse.

    REQ-005: quando `deal_stage` está em `proposal` ou `negotiation` e
    `slot_finder` devolve um slot livre (dentro de 3 dias, 30 min), a
    saída inclui `calendar_slot` e muda `kind` para `meeting_proposal`.
    Sem slot disponível, a saída mantém `kind='email_followup'` e OMITE
    `calendar_slot` — sem fallback silencioso para meeting.
    """
    reference = now if now is not None else datetime.now(UTC)
    proposal_notes = [n for n in notes if _PROPOSAL_KEYWORD.search(n.body)]
    if proposal_notes:
        latest = max(proposal_notes, key=lambda n: n.created_at)
        days_ago = (reference - latest.created_at).days
        plural = "s" if days_ago != 1 else ""
        editable_text = (
            "Olá! Passando para dar continuidade à proposta enviada há "
            f"{days_ago} dia{plural}. Podemos conversar sobre os próximos passos?"
        )
    else:
        editable_text = (
            "Olá! Passando para confirmar seu interesse e entender se posso "
            "ajudar com algo antes de seguirmos."
        )
    result: dict[str, object] = {
        "kind": "email_followup",
        "payload": {},
        "editable_text": editable_text,
    }
    if (
        deal_stage is not None
        and deal_stage in _CALENDAR_SLOT_STAGES
        and slot_finder is not None
    ):
        slot = slot_finder(duration_minutes=30, within_days=3)
        if slot is not None:
            result["kind"] = "meeting_proposal"
            result["calendar_slot"] = slot
    return result


def suggest_all(
    deals: list[Deal],
    *,
    last_note_at: Mapping[str, datetime | None] | None = None,
    now: datetime | None = None,
) -> list[Deal]:
    """Filtra `deals` para os estagnados, mais antigos primeiro, no máximo 10.

    `deals` SHALL vir de `crm_deals`. O chamador resolve a listagem;
    itens que não são `Deal` são ignorados por segurança. `last_note_at`
    mapeia `deal.id` -> timestamp da nota mais recente (ou `None`),
    mesmo contrato de `is_stale`.
    """
    resolved_notes = last_note_at or {}
    reference = now if now is not None else datetime.now(UTC)

    def last_activity(deal: Deal) -> datetime:
        return resolved_notes.get(deal.id) or deal.created_at

    stale = [
        deal
        for deal in deals
        if isinstance(deal, Deal)
        and is_stale(deal, last_note_at=resolved_notes.get(deal.id), now=reference)
    ]
    stale.sort(key=last_activity)
    return stale[:_MAX_SUGGESTIONS]
