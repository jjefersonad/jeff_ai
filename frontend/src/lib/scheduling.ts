/**
 * Client for the scheduled-tasks REST API (`/api/scheduled-tasks`).
 *
 * Calls go through `apiFetch` so the session cookie is attached and 401s
 * trigger the shared re-auth handler, mirroring `usage.ts`. Ownership
 * (`owner_user_key`) is resolved by the backend from the session — never
 * sent by this client. Delivery targeting uses `delivery_channel` names
 * only (`web` / `telegram` / `whatsapp`), never raw user keys.
 */

import { ApiError, apiFetch, parseErrorMessage } from "@/lib/api";

export interface ScheduledTask {
  id: string;
  prompt: string;
  thread_id: string;
  schedule_kind: string;
  schedule_expr: string;
  tool_scope: string;
  skills: string[];
  timeout_seconds: number;
  status: string;
  owner_user_key: string;
  delivery_user_key: string | null;
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
  notify_status: string | null;
  notify_error: string | null;
  created_at: string;
  profile_id: string | null;
}

export interface ScheduledTaskCreatePayload {
  prompt: string;
  schedule_kind: string;
  schedule_expr: string;
  tool_scope?: string;
  skills?: string[];
  timeout_seconds?: number;
  delivery_channel?: string | null;
  profile_id?: string | null;
}

export interface ScheduledTaskUpdatePayload {
  prompt?: string;
  schedule_kind?: string;
  schedule_expr?: string;
  tool_scope?: string;
  skills?: string[];
  delivery_channel?: string | null;
  profile_id?: string | null;
}

export interface DeliveryChannelsResponse {
  channels: string[];
}

async function parseJsonOrThrow<T>(response: Response): Promise<T> {
  if (!response.ok) {
    throw new ApiError(response.status, await parseErrorMessage(response));
  }
  return (await response.json()) as T;
}

/** Fetch the caller's scheduled tasks (all tasks if the caller is admin). */
export async function listScheduledTasks(): Promise<ScheduledTask[]> {
  const response = await apiFetch("/api/scheduled-tasks");
  return parseJsonOrThrow<ScheduledTask[]>(response);
}

/** Canais de entrega disponíveis ao usuário autenticado (+ `web`). */
export async function listDeliveryChannels(): Promise<string[]> {
  const response = await apiFetch("/api/scheduling/delivery-channels");
  const body = await parseJsonOrThrow<DeliveryChannelsResponse>(response);
  return body.channels;
}

/** Create a new scheduled task. */
export async function createScheduledTask(
  payload: ScheduledTaskCreatePayload
): Promise<ScheduledTask> {
  const response = await apiFetch("/api/scheduled-tasks", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  return parseJsonOrThrow<ScheduledTask>(response);
}

/** Update a scheduled task (only allowed while it is still `SCHEDULED`). */
export async function updateScheduledTask(
  id: string,
  payload: ScheduledTaskUpdatePayload
): Promise<ScheduledTask> {
  const response = await apiFetch(`/api/scheduled-tasks/${id}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
  return parseJsonOrThrow<ScheduledTask>(response);
}

/** Cancel (delete) a scheduled task. */
export async function cancelScheduledTask(id: string): Promise<void> {
  const response = await apiFetch(`/api/scheduled-tasks/${id}`, {
    method: "DELETE",
  });
  if (!response.ok) {
    throw new ApiError(response.status, await parseErrorMessage(response));
  }
}

/** Extrai o nome do canal a partir de `delivery_user_key` (`canal:id`). */
export function channelFromDeliveryUserKey(
  deliveryUserKey: string | null | undefined
): string {
  if (!deliveryUserKey) return "web";
  const channel = deliveryUserKey.split(":")[0]?.trim();
  return channel || "web";
}

/** Rótulo amigável para um canal de entrega. */
export function deliveryChannelLabel(channel: string): string {
  switch (channel) {
    case "web":
      return "Web";
    case "telegram":
      return "Telegram";
    case "whatsapp":
      return "WhatsApp";
    default:
      return channel;
  }
}
