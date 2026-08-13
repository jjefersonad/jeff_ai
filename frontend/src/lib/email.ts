/**
 * Client for the email REST API (`/api/email/*`).
 *
 * Two capability surfaces, mirrored from the backend specs:
 *   - `/api/email/accounts*` — connect/list/update/delete IMAP/SMTP accounts
 *     (REQ-001/002/004 of `email-account-management`).
 *   - `/api/email/*`         — list/read/search/organize/send messages
 *     (REQ-001..005 of `email-inbox`).
 *
 * Calls go through `apiFetch` so the session cookie is attached and 401s
 * trigger the shared re-auth handler. Ownership (`user_id`) is resolved by
 * the backend from the session — never sent by this client (REQ-003 of
 * `crm-agent-access` carries over).
 *
 * Pattern lifted from `lib/crm.ts` (typed shapes, `parseJsonOrThrow` helper,
 * `withQuery` builder) and `lib/integrations.ts` (DELETE that resolves on
 * 204 without a body).
 */

import { ApiError, apiFetch, parseErrorMessage } from "@/lib/api";

export type EmailAccountStatus = "connected" | "error" | "syncing";

export interface EmailAccount {
  id: string;
  user_id: string;
  provider: string;
  display_name: string;
  status: EmailAccountStatus | string;
  last_synced_at: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  /**
   * Subset NÃO-secreto da configuração de conexão (REQ-002 do spec
   * `email-account-edit-connection`): o backend preenche esses campos
   * em `EmailAccountResponse` para que o frontend possa abrir o
   * `ConnectAccountDialog` em modo `edit` sem precisar de um GET
   * adicional. **Senhas nunca são retornadas** — o dialog as trata
   * como "manter a senha atual" quando vierem em branco no PATCH.
   * Todos os campos são opcionais porque o backend pode devolvê-los
   * como `null` quando o `user_integration_id` da conta está ausente
   * ou não pertence ao mesmo `user_id`.
   */
  imap_host?: string | null;
  imap_port?: number | null;
  imap_username?: string | null;
  smtp_host?: string | null;
  smtp_port?: number | null;
  smtp_username?: string | null;
}

/**
 * Connect a new IMAP/SMTP account. The backend writes the
 * `EmailAccount` row AND the linked `UserIntegration` (per-field Fernet
 * encryption lives on the latter). Credentials are NEVER echoed back
 * by `EmailAccountResponse` — only `id`/`display_name`/etc. — so this
 * function's return type intentionally omits any `*_password` field.
 */
export interface EmailAccountConnectPayload {
  display_name: string;
  imap_host: string;
  imap_port: number;
  imap_username: string;
  imap_password: string;
  smtp_host: string;
  smtp_port: number;
  smtp_username?: string | null;
  smtp_password?: string | null;
}

export interface EmailAccountUpdatePayload {
  display_name?: string | null;
  is_active?: boolean | null;
}

/**
 * Payload for `PATCH /api/email/accounts/{id}` (REQ-002 do spec
 * `email-account-edit-connection`): edita as configurações de conexão
 * (host/porta/usuário/senha IMAP/SMTP, display_name) de uma conta já
 * conectada. Todos os campos são opcionais: chaves ausentes OU string
 * vazia para as senhas são tratadas pelo backend como "manter o valor
 * atual" — a senha armazenada em `user_integrations.config` é
 * preservada. Credenciais nunca são devolvidas pela resposta.
 */
export interface EmailAccountUpdateConfigPayload {
  display_name?: string | null;
  imap_host?: string | null;
  imap_port?: number | null;
  imap_username?: string | null;
  imap_password?: string | null;
  smtp_host?: string | null;
  smtp_port?: number | null;
  smtp_username?: string | null;
  smtp_password?: string | null;
}

export interface Email {
  id: string;
  email_account_id: string;
  message_id: string;
  thread_id: string | null;
  folder: string;
  from_address: string;
  from_name: string | null;
  to_addresses: string[];
  cc_addresses: string[];
  bcc_addresses: string[];
  subject: string | null;
  body_html: string | null;
  body_text: string | null;
  is_read: boolean;
  is_starred: boolean;
  has_attachments: boolean;
  contact_id: string | null;
  received_at: string;
  created_at: string;
}

/**
 * Move and/or mark an email. Both fields optional; backend requires at
 * least one. `folder=""` is rejected by the backend with 422 (use
 * `null`/omitted when you only want to toggle `is_read`).
 */
export interface EmailUpdatePayload {
  is_read?: boolean;
  folder?: string;
}

export interface SendEmailPayload {
  account_id: string;
  to_addresses: string[];
  subject: string;
  body_text: string;
  body_html?: string | null;
  cc_addresses?: string[] | null;
  bcc_addresses?: string[] | null;
  in_reply_to?: string | null;
  references?: string | null;
}

export interface SendEmailResponse {
  message_id: string;
  sent_at: string;
  thread_id: string | null;
  subject: string | null;
}

async function parseJsonOrThrow<T>(response: Response): Promise<T> {
  if (!response.ok) {
    throw new ApiError(response.status, await parseErrorMessage(response));
  }
  return (await response.json()) as T;
}

function withQuery(
  path: string,
  params: Record<string, string | number | boolean | undefined | null>
): string {
  const qs = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    qs.set(key, String(value));
  }
  const query = qs.toString();
  return query ? `${path}?${query}` : path;
}

// --- Accounts --------------------------------------------------------------

export async function listEmailAccounts(): Promise<EmailAccount[]> {
  const response = await apiFetch("/api/email/accounts");
  return parseJsonOrThrow<EmailAccount[]>(response);
}

export async function getEmailAccount(id: string): Promise<EmailAccount> {
  const response = await apiFetch(`/api/email/accounts/${id}`);
  return parseJsonOrThrow<EmailAccount>(response);
}

export async function connectEmailAccount(
  payload: EmailAccountConnectPayload
): Promise<EmailAccount> {
  const response = await apiFetch("/api/email/accounts", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  return parseJsonOrThrow<EmailAccount>(response);
}

export async function updateEmailAccount(
  id: string,
  payload: EmailAccountUpdatePayload
): Promise<EmailAccount> {
  const response = await apiFetch(`/api/email/accounts/${id}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
  return parseJsonOrThrow<EmailAccount>(response);
}

/**
 * Edita as configurações de conexão (IMAP/SMTP) de uma conta já
 * conectada. O backend filtra `None` e trata senha vazia como "manter
 * a senha atual"; este cliente apenas serializa o payload tal qual.
 */
export async function updateEmailAccountConfig(
  id: string,
  payload: EmailAccountUpdateConfigPayload
): Promise<EmailAccount> {
  const response = await apiFetch(`/api/email/accounts/${id}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
  return parseJsonOrThrow<EmailAccount>(response);
}

export async function deleteEmailAccount(id: string): Promise<void> {
  const response = await apiFetch(`/api/email/accounts/${id}`, {
    method: "DELETE",
  });
  if (!response.ok) {
    throw new ApiError(response.status, await parseErrorMessage(response));
  }
  // 204 No Content — no JSON body to parse.
}

// --- Gmail OAuth -----------------------------------------------------------

/**
 * `POST /api/email/accounts/gmail/authorize` (REQ-001
 * gmail-oauth-connection): pede ao backend a URL de consentimento do
 * Google. O backend gera o `state` (opaco, double-submit cookie) e o
 * devolve embutido na URL; o frontend NÃO toca em cookies, tokens, ou
 * o `state` — só redireciona o navegador para a URL devolvida.
 *
 * O consumidor típico (`ConnectAccountDialog`) faz
 * `window.location.href = (await startGmailOAuth()).authorize_url`. O
 * top-level GET para `accounts.google.com` é SameSite=Lax-safe (o
 * callback usa a sessão existente do backend, verificado por
 * `require_auth` no router).
 */
export interface GmailAuthorizeResponse {
  authorize_url: string;
}

export async function startGmailOAuth(): Promise<GmailAuthorizeResponse> {
  const response = await apiFetch("/api/email/accounts/gmail/authorize", {
    method: "POST",
  });
  return parseJsonOrThrow<GmailAuthorizeResponse>(response);
}

// --- Inbox ------------------------------------------------------------------

export async function listEmails(options?: {
  account_id?: string;
  folder?: string;
  limit?: number;
  offset?: number;
}): Promise<Email[]> {
  const response = await apiFetch(
    withQuery("/api/email", {
      account_id: options?.account_id,
      folder: options?.folder,
      limit: options?.limit,
      offset: options?.offset,
    })
  );
  return parseJsonOrThrow<Email[]>(response);
}

export async function getEmail(id: string): Promise<Email> {
  const response = await apiFetch(`/api/email/${id}`);
  return parseJsonOrThrow<Email>(response);
}

/**
 * Full-text search across the user's own emails (subject / body / from
 * address). Optionally scoped to one account.
 *
 * REQ-003 (email-inbox): results are scoped by `user_id` server-side from
 * the session — there is no parameter for "another user's data" and any
 * cross-user leakage is a backend bug.
 */
export async function searchEmails(
  query: string,
  options?: { account_id?: string; limit?: number }
): Promise<Email[]> {
  const response = await apiFetch(
    withQuery("/api/email/search", {
      q: query,
      account_id: options?.account_id,
      limit: options?.limit,
    })
  );
  return parseJsonOrThrow<Email[]>(response);
}

/**
 * Toggle `is_read` and/or move `folder`. Backend requires at least one
 * of the two to be present (`EmailPatchRequest` validation); passing an
 * empty object would 422. The frontend typically calls this with a
 * single field at a time — `updateEmail(id, { folder: "Archive" })`
 * for a move, or `updateEmail(id, { is_read: true })` to mark read.
 */
export async function updateEmail(
  id: string,
  payload: EmailUpdatePayload
): Promise<Email> {
  const response = await apiFetch(`/api/email/${id}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
  return parseJsonOrThrow<Email>(response);
}

/**
 * Send a new email / reply / forward through the selected account's
 * SMTP credentials. Human-initiated (POST `/api/email/send` from the
 * compose UI) — NOT gated by Tier; the agent tool `send_email` is the
 * one wrapped by `interrupt_on` (REQ-005 email-inbox).
 */
export async function sendEmail(
  payload: SendEmailPayload
): Promise<SendEmailResponse> {
  const response = await apiFetch("/api/email/send", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  return parseJsonOrThrow<SendEmailResponse>(response);
}
