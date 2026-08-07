/**
 * Client for the CRM REST API (`/api/crm/*`).
 *
 * Calls go through `apiFetch` so the session cookie is attached and 401s
 * trigger the shared re-auth handler. Ownership (`user_id`) is resolved by
 * the backend from the session — never sent by this client.
 */

import { ApiError, apiFetch, parseErrorMessage } from "@/lib/api";

export type DealStage =
  | "lead"
  | "qualified"
  | "proposal"
  | "won"
  | "lost";

export interface CrmContact {
  id: string;
  user_id: string;
  name: string;
  email: string | null;
  phone: string | null;
  company_id: string | null;
  status: string | null;
  tags: string[];
  archived_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface CrmCompany {
  id: string;
  user_id: string;
  name: string;
  website: string | null;
  domain: string | null;
  phone: string | null;
  notes: string | null;
  archived_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface CrmDeal {
  id: string;
  user_id: string;
  title: string;
  stage: DealStage | string;
  value: string | number | null;
  currency: string | null;
  contact_id: string | null;
  company_id: string | null;
  archived_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface CrmNote {
  id: string;
  user_id: string;
  body: string;
  source: string;
  contact_id: string | null;
  company_id: string | null;
  deal_id: string | null;
  created_at: string;
}

export interface ContactCreatePayload {
  name: string;
  email?: string | null;
  phone?: string | null;
  company_id?: string | null;
  status?: string | null;
  tags?: string[] | null;
}

export interface ContactUpdatePayload {
  name?: string | null;
  email?: string | null;
  phone?: string | null;
  company_id?: string | null;
  clear_company?: boolean;
  status?: string | null;
  tags?: string[] | null;
}

export interface CompanyCreatePayload {
  name: string;
  website?: string | null;
  domain?: string | null;
  phone?: string | null;
  notes?: string | null;
}

export interface CompanyUpdatePayload {
  name?: string | null;
  website?: string | null;
  domain?: string | null;
  phone?: string | null;
  notes?: string | null;
}

export interface DealCreatePayload {
  title: string;
  stage?: string | null;
  value?: string | number | null;
  currency?: string | null;
  contact_id?: string | null;
  company_id?: string | null;
}

export interface NoteCreatePayload {
  body: string;
  source?: string;
  contact_id?: string | null;
  company_id?: string | null;
  deal_id?: string | null;
}

async function parseJsonOrThrow<T>(response: Response): Promise<T> {
  if (!response.ok) {
    throw new ApiError(response.status, await parseErrorMessage(response));
  }
  return (await response.json()) as T;
}

function withQuery(
  path: string,
  params: Record<string, string | boolean | undefined | null>
): string {
  const qs = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    qs.set(key, String(value));
  }
  const query = qs.toString();
  return query ? `${path}?${query}` : path;
}

// --- Contacts ---------------------------------------------------------------

export async function listContacts(options?: {
  query?: string;
  company_id?: string;
  archived?: boolean;
}): Promise<CrmContact[]> {
  const response = await apiFetch(
    withQuery("/api/crm/contacts", {
      query: options?.query,
      company_id: options?.company_id,
      archived: options?.archived,
    })
  );
  return parseJsonOrThrow<CrmContact[]>(response);
}

export async function getContact(id: string): Promise<CrmContact> {
  const response = await apiFetch(`/api/crm/contacts/${id}`);
  return parseJsonOrThrow<CrmContact>(response);
}

export async function createContact(
  payload: ContactCreatePayload
): Promise<CrmContact> {
  const response = await apiFetch("/api/crm/contacts", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  return parseJsonOrThrow<CrmContact>(response);
}

export async function updateContact(
  id: string,
  payload: ContactUpdatePayload
): Promise<CrmContact> {
  const response = await apiFetch(`/api/crm/contacts/${id}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
  return parseJsonOrThrow<CrmContact>(response);
}

export async function archiveContact(id: string): Promise<CrmContact> {
  const response = await apiFetch(`/api/crm/contacts/${id}/archive`, {
    method: "POST",
  });
  return parseJsonOrThrow<CrmContact>(response);
}

// --- Companies --------------------------------------------------------------

export async function listCompanies(options?: {
  query?: string;
  archived?: boolean;
}): Promise<CrmCompany[]> {
  const response = await apiFetch(
    withQuery("/api/crm/companies", {
      query: options?.query,
      archived: options?.archived,
    })
  );
  return parseJsonOrThrow<CrmCompany[]>(response);
}

export async function getCompany(id: string): Promise<CrmCompany> {
  const response = await apiFetch(`/api/crm/companies/${id}`);
  return parseJsonOrThrow<CrmCompany>(response);
}

export async function createCompany(
  payload: CompanyCreatePayload
): Promise<CrmCompany> {
  const response = await apiFetch("/api/crm/companies", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  return parseJsonOrThrow<CrmCompany>(response);
}

export async function updateCompany(
  id: string,
  payload: CompanyUpdatePayload
): Promise<CrmCompany> {
  const response = await apiFetch(`/api/crm/companies/${id}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
  return parseJsonOrThrow<CrmCompany>(response);
}

export async function archiveCompany(id: string): Promise<CrmCompany> {
  const response = await apiFetch(`/api/crm/companies/${id}/archive`, {
    method: "POST",
  });
  return parseJsonOrThrow<CrmCompany>(response);
}

// --- Deals ------------------------------------------------------------------

export async function listDealStages(): Promise<string[]> {
  const response = await apiFetch("/api/crm/deals/stages");
  return parseJsonOrThrow<string[]>(response);
}

export async function listDeals(options?: {
  stage?: string;
  archived?: boolean;
}): Promise<CrmDeal[]> {
  const response = await apiFetch(
    withQuery("/api/crm/deals", {
      stage: options?.stage,
      archived: options?.archived,
    })
  );
  return parseJsonOrThrow<CrmDeal[]>(response);
}

export async function getDeal(id: string): Promise<CrmDeal> {
  const response = await apiFetch(`/api/crm/deals/${id}`);
  return parseJsonOrThrow<CrmDeal>(response);
}

export async function createDeal(payload: DealCreatePayload): Promise<CrmDeal> {
  const response = await apiFetch("/api/crm/deals", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  return parseJsonOrThrow<CrmDeal>(response);
}

export async function moveDeal(id: string, stage: string): Promise<CrmDeal> {
  const response = await apiFetch(`/api/crm/deals/${id}/move`, {
    method: "POST",
    body: JSON.stringify({ stage }),
  });
  return parseJsonOrThrow<CrmDeal>(response);
}

export async function archiveDeal(id: string): Promise<CrmDeal> {
  const response = await apiFetch(`/api/crm/deals/${id}/archive`, {
    method: "POST",
  });
  return parseJsonOrThrow<CrmDeal>(response);
}

// --- Notes ------------------------------------------------------------------

export async function listNotes(options: {
  contact_id?: string;
  company_id?: string;
  deal_id?: string;
}): Promise<CrmNote[]> {
  const response = await apiFetch(
    withQuery("/api/crm/notes", {
      contact_id: options.contact_id,
      company_id: options.company_id,
      deal_id: options.deal_id,
    })
  );
  return parseJsonOrThrow<CrmNote[]>(response);
}

export async function createNote(payload: NoteCreatePayload): Promise<CrmNote> {
  const response = await apiFetch("/api/crm/notes", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  return parseJsonOrThrow<CrmNote>(response);
}

/** Resultado da validação do formulário de contato (REQ-001 crm-ui). */
export interface ContactFormValidation {
  valid: boolean;
  error?: string;
}

/**
 * Valida campos do formulário de contato antes do submit.
 * Exige `name` e ao menos um identificador (`email` ou `phone`).
 */
export function validateContactForm(input: {
  name: string;
  email?: string | null;
  phone?: string | null;
}): ContactFormValidation {
  const name = input.name?.trim() ?? "";
  const email = input.email?.trim() ?? "";
  const phone = input.phone?.trim() ?? "";
  if (!name) {
    return { valid: false, error: "Nome é obrigatório." };
  }
  if (!email && !phone) {
    return {
      valid: false,
      error: "Informe e-mail ou telefone.",
    };
  }
  return { valid: true };
}

export type CrmUiTab = "contacts" | "companies" | "pipeline";

export type NotesListTarget =
  | { contact_id: string }
  | { company_id: string }
  | { deal_id: string };

/**
 * Resolve o alvo de listagem/criação de notas pela aba ativa.
 *
 * Notas têm exatamente um alvo no backend; a UI NÃO pode misturar
 * seleções residuais de outra aba (ex.: contato ainda selecionado ao
 * abrir um deal no funil).
 */
export function resolveNotesTarget(input: {
  tab: CrmUiTab;
  contactId: string | null;
  companyId: string | null;
  dealId: string | null;
}): NotesListTarget | null {
  if (input.tab === "contacts" && input.contactId) {
    return { contact_id: input.contactId };
  }
  if (input.tab === "companies" && input.companyId) {
    return { company_id: input.companyId };
  }
  if (input.tab === "pipeline" && input.dealId) {
    return { deal_id: input.dealId };
  }
  return null;
}
