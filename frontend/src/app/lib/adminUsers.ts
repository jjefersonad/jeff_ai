/**
 * Client for the admin users REST API (`/api/admin/users`).
 *
 * Same pattern as `mcp.ts` (admin MCP servers): a bare `fetch` with
 * `credentials: 'include'` so the httpOnly session cookie travels. We don't
 * use `apiFetch` here — see the rationale in `mcp.ts` (the 401 handler
 * shared by `apiFetch` redirects to `/public/login`, which is the right
 * behavior for general API calls but not for an admin dialog where the
 * caller wants the error to surface so it can render UI feedback).
 *
 * The backend endpoint is `admin_users_router` (change `user-management`),
 * which uses a `UserPublic` Pydantic response model that lists only the
 * safe fields (`id`, `username`, `role`, `is_active`, `created_at`) — never
 * `password_hash`. See `backend/src/infrastructure/web/admin_users_router.py`.
 *
 * The Next.js rewrite maps `/api/admin/:path*` → backend `/admin/:path*`
 * (note: the FastAPI router uses the `/admin` prefix, not `/api/admin`).
 * See `frontend/next.config.ts`.
 */

export interface AdminUser {
  id: string;
  username: string;
  role: string;
  is_active: boolean;
  created_at: string;
}

const ADMIN_FETCH_INIT: RequestInit = {
  credentials: "include",
};

interface PydanticValidationErrorItem {
  msg?: unknown;
  loc?: unknown;
}

function isPydanticValidationErrorItem(
  item: unknown
): item is PydanticValidationErrorItem {
  return (
    typeof item === "object" &&
    item !== null &&
    typeof (item as PydanticValidationErrorItem).msg === "string"
  );
}

/**
 * FastAPI's built-in Pydantic request validation (422) returns `detail` as
 * an array of `{type, loc, msg, ctx}` objects — not a string. Renders each
 * item's `msg`, prefixed by its field name from `loc` when available, and
 * joins multiple simultaneous errors with "; ".
 */
function formatValidationErrorDetail(items: unknown[]): string | null {
  const messages = items
    .filter(isPydanticValidationErrorItem)
    .map((item) => {
      const msg = item.msg as string;
      const loc = Array.isArray(item.loc) ? item.loc : [];
      const field = loc[loc.length - 1];
      return typeof field === "string" && field !== "body"
        ? `${field}: ${msg}`
        : msg;
    });
  return messages.length > 0 ? messages.join("; ") : null;
}

async function parseErrorDetail(res: Response): Promise<string> {
  try {
    const data = await res.json();
    const { detail } = data ?? {};
    if (typeof detail === "string" && detail) return detail;
    if (Array.isArray(detail)) {
      const formatted = formatValidationErrorDetail(detail);
      if (formatted) return formatted;
    }
    return res.statusText;
  } catch {
    return res.statusText;
  }
}

export async function fetchAdminUsers(): Promise<AdminUser[]> {
  const res = await fetch("/api/admin/users", ADMIN_FETCH_INIT);
  if (!res.ok) throw new Error(await parseErrorDetail(res));
  const data = await res.json();
  return data.users;
}

export interface CreateAdminUserPayload {
  username: string;
  password: string;
  role?: string;
}

export interface CreateAdminUserError extends Error {
  status: number;
}

/**
 * `POST /api/admin/users` — create a new user. Throws an
 * `CreateAdminUserError` carrying the HTTP `status` when the backend rejects
 * the request so the caller can distinguish 422 (validation, e.g. password
 * too short) from 409 (username already taken) and render the right inline
 * feedback in the form without clearing the fields the user already typed.
 */
export async function createAdminUser(
  payload: CreateAdminUserPayload
): Promise<AdminUser> {
  const res = await fetch("/api/admin/users", {
    ...ADMIN_FETCH_INIT,
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const message = await parseErrorDetail(res);
    const err = new Error(message) as CreateAdminUserError;
    err.status = res.status;
    throw err;
  }
  return (await res.json()) as AdminUser;
}

export interface PatchAdminUserPayload {
  role?: string;
  is_active?: boolean;
}

export interface PatchAdminUserError extends Error {
  status: number;
}

/**
 * `PATCH /api/admin/users/{id}` — update `role` and/or `is_active` of a
 * user. Fields omitted in the payload are kept unchanged on the server side
 * (see `backend/src/infrastructure/web/admin_users_router.py:PatchUserRequest`).
 *
 * Throws a `PatchAdminUserError` carrying the HTTP `status` when the
 * backend rejects the request. `409` is the auto-lockout guard (self-disable
 * or last-admin disable) — the caller SHOULD surface the error to the
 * user without updating local state, since the server kept the original
 * value. The page uses this to render an inline alert per row.
 */
export async function patchAdminUser(
  id: string,
  payload: PatchAdminUserPayload
): Promise<AdminUser> {
  const res = await fetch(`/api/admin/users/${encodeURIComponent(id)}`, {
    ...ADMIN_FETCH_INIT,
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const message = await parseErrorDetail(res);
    const err = new Error(message) as PatchAdminUserError;
    err.status = res.status;
    throw err;
  }
  return (await res.json()) as AdminUser;
}
