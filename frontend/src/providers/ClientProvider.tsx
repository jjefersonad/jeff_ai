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
 */

import { createContext, useContext, useMemo, ReactNode } from "react";
import { Client, RequestHook } from "@langchain/langgraph-sdk";
import { getApiBaseUrl } from "@/lib/api";

interface ClientContextValue {
  client: Client;
}

const ClientContext = createContext<ClientContextValue | null>(null);

interface ClientProviderProps {
  children: ReactNode;
  apiKey: string;
}

export function ClientProvider({ children, apiKey }: ClientProviderProps) {
  const client = useMemo(() => {
    // Forces `credentials: 'include'` on every SDK request so the session
    // cookie travels to the backend (see header docstring). The hook is the
    // SDK's documented extension point for per-request `RequestInit`
    // mutations; `credentials` is the only field we need to override.
    const forceCredentialsInclude: RequestHook = (_url, init) => ({
      ...init,
      credentials: "include",
    });

    return new Client({
      apiUrl: getApiBaseUrl(),
      defaultHeaders: {
        "Content-Type": "application/json",
        "X-Api-Key": apiKey,
      },
      onRequest: forceCredentialsInclude,
    });
  }, [apiKey]);

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
