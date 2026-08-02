/**
 * Client for the scheduled-tasks REST API (`/api/scheduled-tasks`).
 *
 * Calls go through `apiFetch` so the session cookie is attached and 401s
 * trigger the shared re-auth handler, mirroring `usage.ts`. Ownership
 * (`owner_user_key`) is resolved by the backend from the session — never
 * sent by this client.
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
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
  created_at: string;
}

export interface ScheduledTaskCreatePayload {
  prompt: string;
  schedule_kind: string;
  schedule_expr: string;
  tool_scope?: string;
  skills?: string[];
  timeout_seconds?: number;
}

export interface ScheduledTaskUpdatePayload {
  prompt?: string;
  schedule_kind?: string;
  schedule_expr?: string;
  tool_scope?: string;
  skills?: string[];
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
