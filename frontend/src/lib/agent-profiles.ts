/**
 * Client for the agent-profiles REST API (`/api/agent-profiles`).
 *
 * Calls go through `apiFetch` so the session cookie is attached and 401s
 * trigger the shared re-auth handler, mirroring `scheduling.ts`. Ownership
 * (`user_id`) is resolved by the backend from the session — never sent by
 * this client. Soft-delete is `POST /{id}/archive`; there is no hard DELETE.
 */

import { ApiError, apiFetch, parseErrorMessage } from "@/lib/api";

export interface AgentProfile {
  id: string;
  user_id: string;
  name: string;
  slug: string;
  system_prompt: string;
  skills_allowlist: string[] | null;
  tools_allowlist: string[] | null;
  mcp_allowlist: string[] | null;
  tier: number;
  model_override: string | null;
  is_active: boolean;
  archived_at: string | null;
  created_at: string;
  updated_at: string;
}

async function parseJsonOrThrow<T>(response: Response): Promise<T> {
  if (!response.ok) {
    throw new ApiError(response.status, await parseErrorMessage(response));
  }
  return (await response.json()) as T;
}

export interface AgentProfileCreatePayload {
  name: string;
  slug: string;
  system_prompt: string;
  skills_allowlist?: string[] | null;
  tools_allowlist?: string[] | null;
  mcp_allowlist?: string[] | null;
  tier?: number;
  model_override?: string | null;
}

export interface AgentProfileUpdatePayload {
  name?: string;
  system_prompt?: string;
  skills_allowlist?: string[] | null;
  tools_allowlist?: string[] | null;
  mcp_allowlist?: string[] | null;
  tier?: number;
  model_override?: string | null;
}

/** Fetch the authenticated user's agent profiles (archived hidden by default). */
export async function listAgentProfiles(): Promise<AgentProfile[]> {
  const response = await apiFetch("/api/agent-profiles");
  return parseJsonOrThrow<AgentProfile[]>(response);
}

/** Create a profile owned by the authenticated user. */
export async function createAgentProfile(
  payload: AgentProfileCreatePayload
): Promise<AgentProfile> {
  const response = await apiFetch("/api/agent-profiles", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  return parseJsonOrThrow<AgentProfile>(response);
}

/** Patch mutable fields of a profile owned by the authenticated user. */
export async function updateAgentProfile(
  id: string,
  payload: AgentProfileUpdatePayload
): Promise<AgentProfile> {
  const response = await apiFetch(`/api/agent-profiles/${id}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
  return parseJsonOrThrow<AgentProfile>(response);
}

/** Soft-archive a profile. There is no hard DELETE. */
export async function archiveAgentProfile(id: string): Promise<AgentProfile> {
  const response = await apiFetch(`/api/agent-profiles/${id}/archive`, {
    method: "POST",
  });
  return parseJsonOrThrow<AgentProfile>(response);
}
