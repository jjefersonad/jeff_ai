/**
 * Thin fetch wrapper used by the frontend for direct REST calls to the
 * backend (login, logout, future endpoints). Three responsibilities:
 *
 * 1. Always sets `credentials: 'include'` so the httpOnly session cookie is
 *    sent on every request — even when the backend is on a different origin
 *    than the frontend (e.g. localhost:3000 → localhost:2024 in `langgraph
 *    dev`). Required by REQ-003 of `frontend-route-guard`.
 *
 * 2. On a 401 response, invokes the handler registered by `setUnauthorizedHandler`
 *    (set by `AuthProvider` in the browser). The handler clears local auth
 *    state and navigates the user to /public/login. Same requirement.
 *
 * 3. Normalises the response: surfaces `detail` from the JSON body when
 *    present, falling back to `statusText`. Used by call sites to surface
 *    login failures etc. without leaking that one field is wrong.
 *
 * NOTE: this wrapper covers only *direct* `fetch` calls. The langgraph-sdk
 * `Client` (used for threads/runs/assistants) is configured separately in
 * `ClientProvider` via the `onRequest` hook to inject `credentials: 'include'`
 * (cookies travel automatically, but the 401 redirect-on-Client-error path
 * is handled by the user navigating naturally to a page that the middleware
 * will then gate).
 */

import { getConfig } from "@/lib/config";

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

type UnauthorizedHandler = () => void;
let unauthorizedHandler: UnauthorizedHandler | null = null;

export function setUnauthorizedHandler(handler: UnauthorizedHandler | null): void {
  unauthorizedHandler = handler;
}

/**
 * Resolve the backend base URL from the user-saved `deploymentUrl` (the same
 * source used by `ClientProvider` for the langgraph-sdk Client). Returns
 * `null` if no config has been saved yet — callers should treat this as
 * "backend not configured" and surface a helpful error to the user.
 */
export function getApiBaseUrl(): string | null {
  const config = getConfig();
  if (!config) return null;
  return config.deploymentUrl.replace(/\/+$/, "");
}

export interface ApiFetchOptions extends Omit<RequestInit, "credentials"> {
  /** Override the backend base URL (e.g. for tests). Defaults to the user-saved deploymentUrl. */
  baseUrl?: string;
}

export async function apiFetch(
  path: string,
  options: ApiFetchOptions = {}
): Promise<Response> {
  const { baseUrl, headers, ...rest } = options;

  const url = baseUrl
    ? `${baseUrl}${path}`
    : (() => {
        const resolved = getApiBaseUrl();
        if (!resolved) {
          throw new ApiError(
            0,
            "Backend URL not configured. Open Settings to set the deployment URL."
          );
        }
        return `${resolved}${path}`;
      })();

  const response = await fetch(url, {
    ...rest,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(headers ?? {}),
    },
  });

  if (response.status === 401 && unauthorizedHandler) {
    unauthorizedHandler();
  }

  return response;
}

/**
 * Parse the JSON body of an error response and return a single, generic
 * message. Backend `HTTPException(detail="Unauthorized")` returns
 * `{"detail": "Unauthorized"}` — we surface that as-is so the caller can show
 * a useful error to the user without exposing which field is wrong.
 */
export async function parseErrorMessage(response: Response): Promise<string> {
  try {
    const data = (await response.json()) as { detail?: unknown } | null;
    if (data && typeof data.detail === "string" && data.detail.length > 0) {
      return data.detail;
    }
  } catch {
    // body wasn't JSON
  }
  return response.statusText || "Request failed";
}
