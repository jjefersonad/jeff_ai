/**
 * Rascunho de follow-up no frontend — espelho de
 * `backend/src/domain/crm/next_best_action.py` (`suggest`).
 *
 * PURO: zero fetch. O chamador resolve as `crm_notes` do deal.
 * Cita só fatos presentes nas notas (ex.: "proposta enviada há 3
 * dias"); sem essa nota, nunca afirma que uma proposta foi enviada.
 */

const MS_PER_DAY = 24 * 60 * 60 * 1000;
const PROPOSAL_KEYWORD = /proposta/i;

const GENERIC_DRAFT =
  "Olá! Passando para confirmar seu interesse e entender se posso " +
  "ajudar com algo antes de seguirmos.";

/**
 * Gera o `editable_text` de `next_best_action.suggest(notes)`.
 * Sem slot de calendário — isso fica no backend (`slot_finder`).
 */
export function suggestFollowupDraft(
  notes: { body: string; created_at: string }[],
  now: Date = new Date()
): string {
  const proposalNotes = notes.filter((note) => PROPOSAL_KEYWORD.test(note.body));
  if (proposalNotes.length === 0) return GENERIC_DRAFT;

  const latest = proposalNotes.reduce((best, note) =>
    Date.parse(note.created_at) >= Date.parse(best.created_at) ? note : best
  );
  const daysAgo = Math.floor(
    (now.getTime() - Date.parse(latest.created_at)) / MS_PER_DAY
  );
  const plural = daysAgo === 1 ? "" : "s";
  return (
    "Olá! Passando para dar continuidade à proposta enviada há " +
    `${daysAgo} dia${plural}. Podemos conversar sobre os próximos passos?`
  );
}
