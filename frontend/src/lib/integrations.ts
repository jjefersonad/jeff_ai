/**
 * Client for the WhatsApp account-linking endpoint
 * (`POST /api/integrations/whatsapp/link-code`, whatsapp-channel REQ-001).
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
