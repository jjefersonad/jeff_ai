/**
 * Detecção de estagnação de deals no frontend — espelho de
 * `backend/src/domain/crm/stagnation.py` (`is_stale`).
 *
 * PURO: zero fetch. O chamador resolve `lastNoteAt` (timestamp da
 * `crm_notes` mais recente daquele deal, ou `null` se nunca houve
 * nota). Limiares por estágio: qualified=7d, proposal=3d,
 * negotiation=2d; won/lost nunca estagnam. `lead` usa o mesmo limiar
 * de `qualified` (7d).
 */

const MS_PER_DAY = 24 * 60 * 60 * 1000;

/** `null` = nunca estagna (won/lost). */
const STALE_THRESHOLD_DAYS: Record<string, number | null> = {
  lead: 7,
  qualified: 7,
  proposal: 3,
  negotiation: 2,
  won: null,
  lost: null,
};

function lastActivityAt(
  deal: { created_at: string },
  lastNoteAt: string | null
): Date {
  return lastNoteAt != null ? new Date(lastNoteAt) : new Date(deal.created_at);
}

/**
 * Indica se o deal não tem sinal de atividade há mais que o limiar
 * do estágio. Sem nota, cai em `deal.created_at` — mesmo contrato
 * do `is_stale` Python.
 */
export function isStale(
  deal: { stage: string; created_at: string },
  lastNoteAt: string | null,
  now: Date = new Date()
): boolean {
  const thresholdDays = STALE_THRESHOLD_DAYS[deal.stage];
  if (thresholdDays == null) return false;
  const lastActivity = lastActivityAt(deal, lastNoteAt);
  return now.getTime() - lastActivity.getTime() > thresholdDays * MS_PER_DAY;
}

/**
 * Dias inteiros desde a última atividade (nota ou `created_at`).
 * Usado no badge `"estagnado Nd"`.
 */
export function daysSinceActivity(
  deal: { created_at: string },
  lastNoteAt: string | null,
  now: Date = new Date()
): number {
  const lastActivity = lastActivityAt(deal, lastNoteAt);
  return Math.floor((now.getTime() - lastActivity.getTime()) / MS_PER_DAY);
}
