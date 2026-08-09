/**
 * Clients for the account-linking endpoints
 * (`POST /api/integrations/{whatsapp,telegram}/link-code`).
 *
 * Calls go through `apiFetch` so the session cookie is attached and 401s
 * trigger the shared re-auth handler.
 */

import { ApiError, apiFetch, parseErrorMessage } from "@/lib/api";

export interface WhatsAppLinkCode {
  code: string;
  expires_at: string;
}

/** Request a new WhatsApp link code for the authenticated user. */
export async function createWhatsAppLinkCode(): Promise<WhatsAppLinkCode> {
  const response = await apiFetch("/api/integrations/whatsapp/link-code", {
    method: "POST",
  });
  if (!response.ok) {
    throw new ApiError(response.status, await parseErrorMessage(response));
  }
  return (await response.json()) as WhatsAppLinkCode;
}

export interface TelegramLinkCode {
  code: string;
  expires_at: string;
}

/** Request a new Telegram link code for the authenticated user. */
export async function createTelegramLinkCode(): Promise<TelegramLinkCode> {
  const response = await apiFetch("/api/integrations/telegram/link-code", {
    method: "POST",
  });
  if (!response.ok) {
    throw new ApiError(response.status, await parseErrorMessage(response));
  }
  return (await response.json()) as TelegramLinkCode;
}
