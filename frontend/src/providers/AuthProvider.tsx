"use client";

/**
 * Authentication context for the Jeff AI frontend.
 *
 * Responsibilities (change `autenticacao-jwt-rotas-protegidas`):
 *  - REQ-004 (frontend-route-guard): expose `login(username, password)`,
 *    `logout()`, `isAuthenticated`, and `user` (with `role` for downstream
 *    gating).
 *  - REQ-003 (frontend-route-guard) — 401 scenario: when `apiFetch` (see
 *    `src/lib/api.ts`) gets a 401, the registered handler is invoked, which
 *    clears local state and redirects to `/public/login`. We register that
 *    handler here on mount and tear it down on unmount.
 *
 * Session rehydration (auth-session-rehydration): on mount we probe
 * `GET /api/me` with a bare `fetch` (NOT `apiFetch` — a 401 here must NOT
 * redirect to login; the cookie may simply be absent on the login page).
 * While the probe is in flight, `isRehydrating` is `true`. On 200 we populate
 * `user`; on 401/network error we leave `user` null.
 *
 * Logout posts to `/public/logout`, which revokes the session server-side
 * (`sessions.revoke_session`) and clears the cookie, then we reset local
 * state and route the user to `/public/login`.
 *
 * `login` returns the response payload so callers can surface backend errors
 * (e.g. invalid credentials) without us throwing — the caller is in a
 * better position to render UI feedback.
 */

import {
  ReactNode,
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { useRouter } from "next/navigation";

import {
  ApiError,
  apiFetch,
  getApiBaseUrl,
  parseErrorMessage,
  setUnauthorizedHandler,
} from "@/lib/api";

export type AuthRole = "admin" | "user";

export interface AuthUser {
  username: string;
  role: AuthRole;
}

export interface LoginResult {
  ok: boolean;
  /** Backend error detail, if any. Generic on purpose — never says which field is wrong. */
  error?: string;
}

interface AuthContextValue {
  isAuthenticated: boolean;
  isAuthenticating: boolean;
  /** True while the mount-time `GET /api/me` probe is in flight. */
  isRehydrating: boolean;
  user: AuthUser | null;
  login: (username: string, password: string) => Promise<LoginResult>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

/** Non-secret mirror of `{username, role}` so admin nav survives remounts / hard reload while `/api/me` is in flight. */
const AUTH_USER_STORAGE_KEY = "jeff_ai.auth.user";

interface AuthProviderProps {
  children: ReactNode;
}

function parseAuthUser(data: unknown): AuthUser | null {
  if (!data || typeof data !== "object") return null;
  const { username, role } = data as { username?: unknown; role?: unknown };
  if (
    typeof username === "string" &&
    (role === "admin" || role === "user")
  ) {
    return { username, role };
  }
  return null;
}

function readCachedUser(): AuthUser | null {
  if (typeof window === "undefined") return null;
  try {
    return parseAuthUser(JSON.parse(sessionStorage.getItem(AUTH_USER_STORAGE_KEY) ?? "null"));
  } catch {
    return null;
  }
}

function writeCachedUser(user: AuthUser | null): void {
  if (typeof window === "undefined") return;
  try {
    if (user) {
      sessionStorage.setItem(AUTH_USER_STORAGE_KEY, JSON.stringify(user));
    } else {
      sessionStorage.removeItem(AUTH_USER_STORAGE_KEY);
    }
  } catch {
    // sessionStorage may be unavailable (private mode quotas) — ignore.
  }
}

export function AuthProvider({ children }: AuthProviderProps) {
  const router = useRouter();
  const [user, setUser] = useState<AuthUser | null>(null);
  const [isAuthenticating, setIsAuthenticating] = useState(false);
  const [isRehydrating, setIsRehydrating] = useState(true);

  const isAuthenticated = user !== null;

  const applyUser = useCallback((next: AuthUser | null) => {
    setUser(next);
    writeCachedUser(next);
  }, []);

  const redirectToLogin = useCallback(() => {
    applyUser(null);
    if (typeof window === "undefined") return;
    const current = `${window.location.pathname}${window.location.search}`;
    const safe = current.startsWith("/") && !current.startsWith("//") && !current.includes("://")
      ? current
      : "/";
    const target = safe === "/" ? "/public/login" : `/public/login?redirect=${encodeURIComponent(safe)}`;
    router.replace(target);
  }, [router, applyUser]);

  // Register the 401 interceptor: any apiFetch 401 will reset state and bounce
  // the user to /public/login. Unregisters on unmount to avoid leaks if the
  // provider is ever torn down (e.g. tests, HMR boundaries).
  useEffect(() => {
    setUnauthorizedHandler(redirectToLogin);
    return () => setUnauthorizedHandler(null);
  }, [redirectToLogin]);

  // Rehydrate React auth state from sessionStorage (optimistic) + GET /api/me
  // (authoritative). Bare fetch on purpose: apiFetch would redirect to
  // /public/login on 401, which is wrong for a probe.
  useEffect(() => {
    let cancelled = false;
    const cached = readCachedUser();
    if (cached) setUser(cached);

    const base = getApiBaseUrl();
    if (!base) {
      setIsRehydrating(false);
      return;
    }

    (async () => {
      try {
        const response = await fetch(`${base}/api/me`, {
          credentials: "include",
        });
        if (cancelled) return;
        if (response.ok) {
          const parsed = parseAuthUser(await response.json());
          if (parsed) applyUser(parsed);
        } else if (response.status === 401) {
          // Cookie gone/expired — drop the optimistic cache.
          applyUser(null);
        }
        // Other errors (404, 5xx): keep the cached user so admin nav does
        // not disappear when the probe endpoint is briefly unavailable.
      } catch {
        // Network blip — keep cache; protected calls will 401 later if needed.
      } finally {
        if (!cancelled) setIsRehydrating(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [applyUser]);

  const login = useCallback(
    async (username: string, password: string): Promise<LoginResult> => {
      setIsAuthenticating(true);
      try {
        // Bare fetch: a 401 here is "wrong password", not "session expired".
        // Using apiFetch would fire the global unauthorized handler and
        // bounce the user while they're still on the login form.
        const base = getApiBaseUrl();
        if (!base) {
          return {
            ok: false,
            error:
              "API URL not configured. Set NEXT_PUBLIC_API_URL in the frontend environment.",
          };
        }
        const response = await fetch(`${base}/public/login`, {
          method: "POST",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ username, password }),
        });
        if (response.ok) {
          const parsed = parseAuthUser(await response.json());
          if (parsed) {
            applyUser(parsed);
            return { ok: true };
          }
          // Defensive: backend should always return username+role, but if a
          // future change breaks the contract, treat it as a hard failure
          // rather than half-authenticating.
          return { ok: false, error: "Malformed login response" };
        }
        return { ok: false, error: await parseErrorMessage(response) };
      } catch (error) {
        if (error instanceof ApiError) {
          return { ok: false, error: error.message };
        }
        return { ok: false, error: "Network error" };
      } finally {
        setIsAuthenticating(false);
      }
    },
    [applyUser]
  );

  const logout = useCallback(async () => {
    try {
      await apiFetch("/public/logout", { method: "POST" });
    } catch {
      // Even if the call fails (e.g. backend already down), we still want
      // to clear local state and route the user to /public/login.
    }
    applyUser(null);
    router.replace("/public/login");
  }, [router, applyUser]);

  const value = useMemo<AuthContextValue>(
    () => ({
      isAuthenticated,
      isAuthenticating,
      isRehydrating,
      user,
      login,
      logout,
    }),
    [isAuthenticated, isAuthenticating, isRehydrating, user, login, logout]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
