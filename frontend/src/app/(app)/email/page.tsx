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
 */

import { useCallback, useEffect, useState } from "react";
import { Mail } from "lucide-react";

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

export default function EmailPage() {
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
