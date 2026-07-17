"use client";

/**
 * Login page for the Jeff AI frontend.
 *
 * Lives at /public/login — which the middleware (`src/middleware.ts`) treats as
 * a public path, so unauthenticated users can reach it without being redirected
 * elsewhere. This satisfies REQ-002 of `public-endpoints` ("/public/login
 * renderiza sem redirecionamento mesmo sem sessão") and the matching
 * acceptance criterion in the change's `task-frontend-3`.
 *
 * On successful login, the user is bounced to `?redirect=<path>` (set by the
 * middleware when it intercepted an unauthenticated request), sanitised to
 * same-app relative paths only — see `sanitizeRedirectTarget` (mirrored from
 * `src/middleware.ts` to keep the rule in one place would be ideal, but the
 * edge runtime forbids importing shared modules, so the rule is duplicated and
 * must stay in lock-step). REQ-002 of `frontend-route-guard` ("Redirect
 * sanitizado").
 *
 * On failure, we surface the backend's `detail` field verbatim (generic on
 * purpose, per REQ-003 of `public-endpoints` — the backend never says which
 * field is wrong, so neither do we).
 *
 * If the user lands here while already authenticated (e.g. by manually typing
 * the URL), we don't auto-redirect to the protected area: REQ-005 of
 * `frontend-route-guard` says the cookie is the only source of truth, and
 * `isAuthenticated` in `AuthProvider` is React state that may be stale across
 * a hard reload. Keeping the user on the login page is safer than guessing.
 */

import { FormEvent, Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { LogIn } from "lucide-react";

import { useAuth } from "@/providers/AuthProvider";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

const DEFAULT_PROTECTED_PATH = "/";

/**
 * Mirrors the sanitisation rule from `src/middleware.ts:sanitizeRedirectTarget`.
 * Both copies must accept the same set of values — protocol-relative
 * (`//evil.com`) and absolute (`https://evil.com`) targets are rejected to
 * prevent open redirects.
 */
function sanitizeRedirectTarget(candidate: string | null): string {
  if (!candidate) return DEFAULT_PROTECTED_PATH;
  if (!candidate.startsWith("/") || candidate.startsWith("//")) {
    return DEFAULT_PROTECTED_PATH;
  }
  if (candidate.includes("://")) return DEFAULT_PROTECTED_PATH;
  return candidate;
}

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { login, isAuthenticating } = useAuth();

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);

    const result = await login(username, password);
    if (result.ok) {
      const target = sanitizeRedirectTarget(searchParams.get("redirect"));
      router.replace(target);
      return;
    }
    setError(result.error ?? "Login failed");
  };

  return (
    <form
      onSubmit={handleSubmit}
      className="flex w-full max-w-sm flex-col gap-4 rounded-lg border border-border bg-card p-6 shadow-sm"
    >
      <div className="flex flex-col gap-1">
        <h1 className="text-xl font-semibold">Sign in</h1>
        <p className="text-sm text-muted-foreground">
          Use your Jeff AI account to continue.
        </p>
      </div>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="username">Username</Label>
        <Input
          id="username"
          name="username"
          type="text"
          autoComplete="username"
          required
          value={username}
          onChange={(event) => setUsername(event.target.value)}
          disabled={isAuthenticating}
        />
      </div>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="password">Password</Label>
        <Input
          id="password"
          name="password"
          type="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          disabled={isAuthenticating}
        />
      </div>

      {error && (
        <p
          role="alert"
          className="text-sm text-destructive"
        >
          {error}
        </p>
      )}

      <Button
        type="submit"
        disabled={isAuthenticating || username.length === 0 || password.length === 0}
      >
        <LogIn className="h-4 w-4" />
        {isAuthenticating ? "Signing in…" : "Sign in"}
      </Button>
    </form>
  );
}

export default function LoginPage() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-background p-6">
      <Suspense
        fallback={
          <div
            className="text-sm text-muted-foreground"
            role="status"
          >
            Loading…
          </div>
        }
      >
        <LoginForm />
      </Suspense>
    </main>
  );
}
