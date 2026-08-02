/**
 * Client for admin token-usage reporting (`GET /api/usage`).
 *
 * Calls go through `apiFetch` so the session cookie is attached and 401s
 * trigger the shared re-auth handler. Authorization (admin-only) is enforced
 * by the backend via `require_admin`; this module only shapes the query.
 */

import { ApiError, apiFetch, parseErrorMessage } from "@/lib/api";

export interface UsageFilters {
  user_key?: string;
  from?: string;
  to?: string;
  provider?: string;
  model?: string;
}

export interface UsageTotals {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  user_key?: string;
  filters: Record<string, unknown>;
}

export interface FetchUsageParams {
  from?: string;
  to?: string;
  user_key?: string;
  provider?: string;
  model?: string;
}

/** Build `/api/usage?...` with only defined filter params. */
export function buildUsagePath(params: FetchUsageParams = {}): string {
  const search = new URLSearchParams();
  if (params.from) search.set("from", params.from);
  if (params.to) search.set("to", params.to);
  if (params.user_key) search.set("user_key", params.user_key);
  if (params.provider) search.set("provider", params.provider);
  if (params.model) search.set("model", params.model);
  const qs = search.toString();
  return qs ? `/api/usage?${qs}` : "/api/usage";
}

/** Fetch aggregated token usage for the given filters (admin-only API). */
export async function fetchUsage(
  params: FetchUsageParams = {}
): Promise<UsageTotals> {
  const response = await apiFetch(buildUsagePath(params));
  if (!response.ok) {
    throw new ApiError(response.status, await parseErrorMessage(response));
  }
  return (await response.json()) as UsageTotals;
}
