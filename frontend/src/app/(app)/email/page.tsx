"use client";

/**
 * `/email` — IMAP/SMTP email client (email-client-imap-mvp design Decision 7).
 *
 * Exactly two top-level tabs:
 *   - "Caixa de Entrada" — rendered by `InboxPanel` (task-frontend-3).
 *   - "Contas" — rendered by `AccountsPanel` (frontend-2; connect/edit/remove).
 *
 * `ComposeDialog` is a modal owned here — composing is not a navigable
 * destination. Its trigger ("Nova mensagem") lives in `InboxPanel`'s
 * toolbar (email-inbox-ux-improvements REQ-007); this page only owns the
 * dialog's open state and the compose pre-fill (built by `InboxPanel` for
 * Reply/Forward).
 *
 * Mirrors the `(app)/crm/page.tsx` pattern: shared state lives here so
 * the "Contas" tab can notify the inbox of account changes when accounts
 * are connected/edited/removed.
 *
 * OAuth callback handling (gmail-account-oauth-connection REQ-002 /
 * REQ-004): the backend redirects the browser back to
 * `{FRONTEND_ORIGIN}/email?gmail_connected=1|0` after the Google
 * consent flow finishes. This page reads that param on mount, shows
 * a success/error toast, refetches the accounts list on success, and
 * strips the param from the URL via `history.replaceState` — NOT via
 * `router.replace`, which would re-mount the page and re-fire the
 * effect (duplicate toasts / refetches).
 */

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { Mail } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { toast } from "sonner";

import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs";
import { ApiError } from "@/lib/api";
import { listEmailAccounts, type EmailAccount } from "@/lib/email";

import { AccountsPanel } from "./AccountsPanel";
import { ComposeDialog, type ComposePrefill } from "./ComposeDialog";
import { InboxPanel } from "./InboxPanel";

type TabId = "inbox" | "accounts";

function errMessage(err: unknown): string {
  return err instanceof ApiError ? err.message : "Falha inesperada";
}

/**
 * Devolve o `pathname + search` atual com `gmail_connected` removido.
 * Preserva qualquer outro query param que possa estar na URL.
 */
function stripGmailConnected(href: string): string {
  try {
    // `window.location.href` é absoluto; o `history.replaceState` aceita
    // um URL absoluto OU relativo. Construímos um `URL` para manipular
    // os search params de forma robusta e devolvemos o resultado
    // (pathname + search) — assim não dependemos do origin.
    const url = new URL(href);
    if (!url.searchParams.has("gmail_connected")) return href;
    url.searchParams.delete("gmail_connected");
    return url.pathname + (url.search ? url.search : "") + url.hash;
  } catch {
    return href;
  }
}

function EmailPageContent() {
  const [tab, setTab] = useState<TabId>("inbox");
  const [composeOpen, setComposeOpen] = useState(false);
  const [composePrefill, setComposePrefill] = useState<ComposePrefill | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Shared account list — the inbox filter dropdown needs the full list
  // (per `InboxPanel` props), not just the count. Refreshed on mount and
  // whenever AccountsPanel signals a change.
  const [accounts, setAccounts] = useState<EmailAccount[]>([]);
  const refreshAccounts = useCallback(async () => {
    try {
      const list = await listEmailAccounts();
      setAccounts(list);
    } catch (err) {
      setError(errMessage(err));
    }
  }, []);

  useEffect(() => {
    refreshAccounts();
  }, [refreshAccounts]);

  // OAuth callback handling: ler `?gmail_connected=1|0` uma vez (no
  // mount) e mostrar o toast correspondente. O `history.replaceState`
  // evita que a próxima navegação/save re-monte o componente e re-dispare
  // o mesmo efeito. O `useRef` impede que o efeito re-rode com o mesmo
  // valor de flag (em React 19, `useSearchParams` devolve um objeto novo
  // a cada render e dispararia o efeito duas vezes em dev strict mode).
  const searchParams = useSearchParams();
  const handledGmailConnected = useRef(false);
  useEffect(() => {
    if (typeof window === "undefined") return;
    if (handledGmailConnected.current) return;
    const flag = searchParams.get("gmail_connected");
    if (flag === null) return;
    handledGmailConnected.current = true;
    if (flag === "1") {
      toast.success("Conta Google conectada com sucesso.");
      // Refetch já é feito pelo `useEffect` de mount — o AccountsPanel
      // mostra a nova conta. Um refetch extra aqui garante que
      // apareça mesmo se o usuário chegou via redirect externo
      // (auth flow não preserva o state de navegação).
      void refreshAccounts();
    } else if (flag === "0") {
      toast.error("Conexão com Google não concluída. Tente novamente.");
    }
    // Strip the param without re-mounting.
    const stripped = stripGmailConnected(window.location.href);
    window.history.replaceState(null, "", stripped);
  }, [searchParams, refreshAccounts]);

  const openCompose = useCallback((prefill?: ComposePrefill) => {
    setComposePrefill(prefill ?? null);
    setComposeOpen(true);
  }, []);

  const closeCompose = useCallback((next: boolean) => {
    setComposeOpen(next);
    if (!next) setComposePrefill(null);
  }, []);

  return (
    <div className="min-h-screen bg-background">
      <header className="sticky top-0 z-40 border-b border-border bg-background/80 backdrop-blur-sm">
        <div className="mx-auto flex max-w-6xl items-center gap-3 px-6 py-4">
          <Mail size={24} className="text-primary" aria-hidden="true" />
          <h1 className="text-xl font-semibold">Email</h1>
        </div>
      </header>

      <main className="mx-auto flex max-w-6xl flex-col gap-6 px-6 py-8">
        {error && (
          <p className="text-sm text-destructive" role="alert">
            {error}
          </p>
        )}

        <Tabs value={tab} onValueChange={(value) => setTab(value as TabId)}>
          <TabsList>
            <TabsTrigger value="inbox">Caixa de Entrada</TabsTrigger>
            <TabsTrigger value="accounts">Contas</TabsTrigger>
          </TabsList>

          <TabsContent value="inbox" className="mt-4">
            <InboxPanel
              accounts={accounts}
              onCompose={(prefill) => openCompose(prefill)}
            />
          </TabsContent>

          <TabsContent value="accounts" className="mt-4">
            <AccountsPanel onAccountsChanged={refreshAccounts} />
          </TabsContent>
        </Tabs>
      </main>

      <ComposeDialog
        open={composeOpen}
        onOpenChange={closeCompose}
        prefill={composePrefill}
        accounts={accounts}
      />
    </div>
  );
}

export default function EmailPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen bg-background">
          <p className="p-6 text-sm text-muted-foreground" role="status">
            Carregando…
          </p>
        </div>
      }
    >
      <EmailPageContent />
    </Suspense>
  );
}
