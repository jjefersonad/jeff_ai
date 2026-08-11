/**
 * Clients for `/api/integrations` — listing/deleting a user's registered
 * `UserIntegration`s, and the account-linking endpoints
 * (`POST /api/integrations/{whatsapp,telegram}/link-code`).
 *
 * Calls go through `apiFetch` so the session cookie is attached and 401s
 * trigger the shared re-auth handler.
 */

import type { LucideIcon } from "lucide-react";
import { Mail, MessageCircle, Plug, Send } from "lucide-react";

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

export interface UserIntegration {
  id: string;
  user_id: string;
  integration_type: string;
  config: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

/**
 * Shape returned by `GET /api/integrations`. `config` is `null` for entries
 * an admin caller doesn't own (the backend never leaks another user's
 * secrets — REQ-004 of `user-integration-credentials-store`).
 */
export type UserIntegrationSummary = UserIntegration;

/** List the caller's `UserIntegration`s (admin sees all, without others' config). */
export async function listUserIntegrations(): Promise<UserIntegrationSummary[]> {
  const response = await apiFetch("/api/integrations");
  if (!response.ok) {
    throw new ApiError(response.status, await parseErrorMessage(response));
  }
  return (await response.json()) as UserIntegrationSummary[];
}

/** Delete a `UserIntegration` by id. Resolves on 204; throws `ApiError` otherwise. */
export async function deleteUserIntegration(id: string): Promise<void> {
  const response = await apiFetch(`/api/integrations/${id}`, {
    method: "DELETE",
  });
  if (!response.ok) {
    throw new ApiError(response.status, await parseErrorMessage(response));
  }
}

interface IntegrationTypeMeta {
  label: string;
  icon: LucideIcon;
}

const INTEGRATION_TYPE_LABELS: Record<string, IntegrationTypeMeta> = {
  telegram: { label: "Telegram", icon: Send },
  whatsapp_business: { label: "WhatsApp Business", icon: MessageCircle },
  smtp: { label: "SMTP", icon: Mail },
};

/** Friendly label/icon for an `integration_type`; falls back safely for unknown types. */
export function getIntegrationTypeMeta(integrationType: string): IntegrationTypeMeta {
  return (
    INTEGRATION_TYPE_LABELS[integrationType] ?? { label: integrationType, icon: Plug }
  );
}

/**
 * Public config values needed to build deep links for the channel-linking flow.
 * Fetched once per `AddIntegrationDialog` mount (channel-link-wiring design Decision 5).
 * `null` when the operator has not configured the corresponding env var.
 */
export interface ChannelLinkConfig {
  telegram_bot_username: string | null;
  whatsapp_business_number: string | null;
}

/** `GET /api/integrations/channel-config` (channel-link-deep-links REQ-002). */
export async function getChannelLinkConfig(): Promise<ChannelLinkConfig> {
  const response = await apiFetch("/api/integrations/channel-config");
  if (!response.ok) {
    throw new ApiError(response.status, await parseErrorMessage(response));
  }
  return (await response.json()) as ChannelLinkConfig;
}

/** Build the deep-link href for a generated link code, or `undefined` if config is missing. */
export function buildDeepLinkHref(
  type: "whatsapp" | "telegram",
  code: string,
  config: ChannelLinkConfig,
): string | undefined {
  if (type === "telegram" && config.telegram_bot_username) {
    return `https://t.me/${config.telegram_bot_username}?start=${code}`;
  }
  if (type === "whatsapp" && config.whatsapp_business_number) {
    return `https://wa.me/${config.whatsapp_business_number}?text=${code}`;
  }
  return undefined;
}
