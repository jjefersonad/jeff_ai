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
 * Resolve the backend base URL from `NEXT_PUBLIC_API_URL` (the same source
 * used by `ClientProvider` for the langgraph-sdk Client). Jeff AI is
 * self-hosted with exactly one backend deployment, so this is fixed at
 * build/container-start time — not something the user configures per browser.
 * Returns `""` if the env var is missing — callers should treat that as a
 * deployment misconfiguration.
 */
export function getApiBaseUrl(): string {
  return (process.env.NEXT_PUBLIC_API_URL ?? "").replace(/\/+$/, "");
}

export interface ApiFetchOptions extends Omit<RequestInit, "credentials"> {
  /** Override the backend base URL (e.g. for tests). Defaults to NEXT_PUBLIC_API_URL. */
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
            "API URL not configured. Set NEXT_PUBLIC_API_URL in the frontend environment."
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

export type DownloadErrorKind = "unauthorized" | "not_found" | "server_error";

/**
 * Thrown by `downloadAuthenticatedFile` so callers can distinguish an expired/missing
 * session from a genuinely missing file or a server error, instead of treating every
 * failure the same way.
 */
export class DownloadError extends ApiError {
  readonly kind: DownloadErrorKind;

  constructor(status: number, message: string, kind: DownloadErrorKind) {
    super(status, message);
    this.name = "DownloadError";
    this.kind = kind;
  }
}

function downloadErrorKind(status: number): DownloadErrorKind {
  if (status === 401) return "unauthorized";
  if (status === 404) return "not_found";
  return "server_error";
}

/** Resolves `url` (relative or absolute) to a path, against the current page origin. */
function toPath(url: string): string {
  const parsed = new URL(url, window.location.origin);
  return `${parsed.pathname}${parsed.search}`;
}

/**
 * Downloads a session-protected file (e.g. a generated `/api/files/docx/...` document)
 * by fetching it with credentials attached and saving the response as a blob, instead of
 * letting the browser navigate directly to the URL.
 *
 * A bare `<a href download>` pointed at an absolute document URL can silently drop the
 * `SameSite=Strict` session cookie when the browser's current origin doesn't match the
 * URL's origin, surfacing the browser's own generic download-failure UI instead of an
 * app-controlled 401. Fetching through `apiFetch` (credentials always included, resolved
 * against the backend's own origin) and building the download from the resulting blob
 * sidesteps that regardless of the exact cross-origin mechanism at play.
 */
export async function downloadAuthenticatedFile(
  url: string,
  filename: string
): Promise<void> {
  const response = await apiFetch(toPath(url));

  if (!response.ok) {
    const message = await parseErrorMessage(response);
    throw new DownloadError(response.status, message, downloadErrorKind(response.status));
  }

  const blob = await response.blob();
  const objectUrl = URL.createObjectURL(blob);
  try {
    const link = document.createElement("a");
    link.href = objectUrl;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  } finally {
    URL.revokeObjectURL(objectUrl);
  }
}
