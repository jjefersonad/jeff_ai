"use client";

/**
 * Provides the langgraph-sdk `Client` used by the chat UI to talk to the
 * Jeff AI backend (threads, runs, assistants, etc).
 *
 * Since the change `autenticacao-jwt-rotas-protegidas`, the backend requires a
 * session cookie on every protected request. The browser's default
 * `credentials: 'same-origin'` only sends cookies for same-origin requests,
 * which fails since the backend (`NEXT_PUBLIC_API_URL`, see `getApiBaseUrl`)
 * is a different origin from the frontend (e.g. localhost:3002 →
 * localhost:8001). We use the SDK's `onRequest` hook to force
 * `credentials: 'include'` on every request so the httpOnly session cookie is
 * sent regardless of origin (REQ-003 of `frontend-route-guard`).
 *
 * Since the change `session-expiry-redirect-to-login`, the `Client` is also
 * given a custom `callerOptions.fetch` (`fetchWithUnauthorizedCheck`). Every
 * `BaseClient` subclass (threads, runs/streaming, assistants, crons) funnels
 * through that one fetch implementation, so a 401 from any of them — chat
 * streaming via `useStream`, thread listing/deletion via `useThreads`, etc —
 * triggers the same `unauthorizedHandler`/`redirectToLogin` that `apiFetch`
 * already triggers for REST calls (REQ-003).
 */

import { createContext, useContext, useMemo, ReactNode } from "react";
import { Client, RequestHook } from "@langchain/langgraph-sdk";
import { checkUnauthorized, getApiBaseUrl } from "@/lib/api";

/**
 * Custom `fetch` passed to the SDK `Client` via `callerOptions.fetch`. Mirrors
 * the native `fetch` signature exactly (so `AsyncCaller.fetch(...args)` can
 * call it positionally) and forwards to the real `fetch` unchanged, checking
 * the response for a 401 before returning it — without consuming its body.
 */
export const fetchWithUnauthorizedCheck: typeof fetch = async (...args) => {
  const response = await fetch(...args);
  checkUnauthorized(response);
  return response;
};

interface ClientContextValue {
  client: Client;
}

const ClientContext = createContext<ClientContextValue | null>(null);

interface ClientProviderProps {
  children: ReactNode;
}

export function ClientProvider({ children }: ClientProviderProps) {
  const client = useMemo(() => {
    // Forces `credentials: 'include'` on every SDK request so the session
    // cookie travels to the backend (see header docstring). The hook is the
    // SDK's documented extension point for per-request `RequestInit`
    // mutations; `credentials` is the only field we need to override.
    //
    // Note: the previous implementation also injected an `X-Api-Key` header
    // carrying a LangSmith key from the browser. That header is no longer
    // sent — the backend never read it (auth is session-cookie-only via
    // `require_auth`), and the key now lives on the backend as
    // `LANGSMITH_API_KEY` (see `langsmith-api-key-config`).
    const forceCredentialsInclude: RequestHook = (_url, init) => ({
      ...init,
      credentials: "include",
    });

    return new Client({
      apiUrl: getApiBaseUrl(),
      defaultHeaders: {
        "Content-Type": "application/json",
      },
      onRequest: forceCredentialsInclude,
      callerOptions: { fetch: fetchWithUnauthorizedCheck },
    });
  }, []);

  const value = useMemo(() => ({ client }), [client]);

  return (
    <ClientContext.Provider value={value}>{children}</ClientContext.Provider>
  );
}

export function useClient(): Client {
  const context = useContext(ClientContext);

  if (!context) {
    throw new Error("useClient must be used within a ClientProvider");
  }
  return context.client;
}
