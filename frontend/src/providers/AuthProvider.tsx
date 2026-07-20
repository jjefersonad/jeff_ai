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
 * The state is intentionally React-only: the httpOnly session cookie is the
 * source of truth on the server. We don't try to probe `/public/me` on mount
 * (no such endpoint exists in the backend), so the initial `isAuthenticated`
 * is `false` and only flips to `true` after a successful `login()`. The
 * cookie's *presence* is sufficient for the middleware (`src/middleware.ts`)
 * to let the user through on a hard reload; the first 401 from any protected
 * call (if the cookie is stale/expired) will bounce the user back to login.
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
  user: AuthUser | null;
  login: (username: string, password: string) => Promise<LoginResult>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

interface AuthProviderProps {
  children: ReactNode;
}

export function AuthProvider({ children }: AuthProviderProps) {
  const router = useRouter();
  const [user, setUser] = useState<AuthUser | null>(null);
  const [isAuthenticating, setIsAuthenticating] = useState(false);

  const isAuthenticated = user !== null;

  const redirectToLogin = useCallback(() => {
    setUser(null);
    if (typeof window === "undefined") return;
    const current = `${window.location.pathname}${window.location.search}`;
    const safe = current.startsWith("/") && !current.startsWith("//") && !current.includes("://")
      ? current
      : "/";
    const target = safe === "/" ? "/public/login" : `/public/login?redirect=${encodeURIComponent(safe)}`;
    router.replace(target);
  }, [router]);

  // Register the 401 interceptor: any apiFetch 401 will reset state and bounce
  // the user to /public/login. Unregisters on unmount to avoid leaks if the
  // provider is ever torn down (e.g. tests, HMR boundaries).
  useEffect(() => {
    setUnauthorizedHandler(redirectToLogin);
    return () => setUnauthorizedHandler(null);
  }, [redirectToLogin]);

  const login = useCallback(
    async (username: string, password: string): Promise<LoginResult> => {
      setIsAuthenticating(true);
      try {
        const response = await apiFetch("/public/login", {
          method: "POST",
          body: JSON.stringify({ username, password }),
        });
        if (response.ok) {
          const data = (await response.json()) as {
            username?: unknown;
            role?: unknown;
          };
          if (
            typeof data.username === "string" &&
            (data.role === "admin" || data.role === "user")
          ) {
            setUser({ username: data.username, role: data.role });
            return { ok: true };
          }
          // Defensive: backend should always return username+role, but if a
          // future change breaks the contract, treat it as a hard failure
          // rather than half-authenticating.
          return { ok: false, error: "Malformed login response" };
        }
        return { ok: false, error: await parseErrorMessage(response) };
      } catch (error) {
        // apiFetch throws ApiError(0, "API URL not configured…") when
        // NEXT_PUBLIC_API_URL is missing from the frontend environment.
        // Surface the message verbatim.
        if (error instanceof ApiError) {
          return { ok: false, error: error.message };
        }
        return { ok: false, error: "Network error" };
      } finally {
        setIsAuthenticating(false);
      }
    },
    []
  );

  const logout = useCallback(async () => {
    try {
      await apiFetch("/public/logout", { method: "POST" });
    } catch {
      // Even if the call fails (e.g. backend already down), we still want
      // to clear local state and route the user to /public/login.
    }
    setUser(null);
    router.replace("/public/login");
  }, [router]);

  const value = useMemo<AuthContextValue>(
    () => ({ isAuthenticated, isAuthenticating, user, login, logout }),
    [isAuthenticated, isAuthenticating, user, login, logout]
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
