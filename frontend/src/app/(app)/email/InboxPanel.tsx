"use client";

/**
 * "Caixa de Entrada" tab panel for `/email` (REQ-001..004 email-inbox).
 *
 * One single component serving every folder (design Decision 7):
 *   - folder selector (Inbox / Sent / Drafts / Trash / Spam + any custom
 *     folder that surfaces in the loaded emails — IMAP providers expose
 *     arbitrary folder names, and there is no `GET /api/email/folders`
 *     endpoint in this MVP);
 *   - account filter ("all accounts" / one specific account_id);
 *   - paginated email list scoped by folder + account, full width (no
 *     split pane — email-inbox-ux-improvements REQ-009);
 *   - row/card activation navigates to `/email/{id}` with `folder`,
 *     `account`, and `q` query params (email-detail-full-page REQ-009 /
 *     REQ-017). List filters are synced onto `/email` search params
 *     without dropping extras such as `gmail_connected`;
 *   - search via `searchEmails` (REQs REQ-003 + REQ-002 of inbox).
 *
 * Reading chrome, reply/forward, and move/delete live on `EmailReadView`.
 * "Nova mensagem" still opens the page-owned `ComposeDialog` via `onCompose`.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  ChevronLeft,
  ChevronRight,
  Inbox,
  Mail,
  MailOpen,
  Pencil,
  Search,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/lib/api";
import {
  listEmails,
  searchEmails,
  type Email,
  type EmailAccount,
} from "@/lib/email";

import type { ComposePrefill } from "./ComposeDialog";

const STANDARD_FOLDERS = ["Inbox", "Sent", "Drafts", "Trash", "Spam"] as const;
type StandardFolder = (typeof STANDARD_FOLDERS)[number];
/** Either a standard IMAP folder or a custom one surfaced by the account. */
type FolderName = StandardFolder | (string & {});

const PAGE_SIZE = 25;

function errMessage(err: unknown): string {
  return err instanceof ApiError ? err.message : "Falha inesperada";
}

function folderLabel(folder: string): string {
  // Display labels for the standard IMAP folder names; custom folders
  // are passed through verbatim (no localization — they come from the
  // user's IMAP server in their own language).
  const map: Record<StandardFolder, string> = {
    Inbox: "Caixa de Entrada",
    Sent: "Enviados",
    Drafts: "Rascunhos",
    Trash: "Lixeira",
    Spam: "Spam",
  };
  if ((STANDARD_FOLDERS as readonly string[]).includes(folder)) {
    return map[folder as StandardFolder];
  }
  return folder;
}

function formatReceivedAt(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString();
}

function folderFromSearch(value: string | null): FolderName {
  return value && value.length > 0 ? value : "Inbox";
}

/** Merge list-context filters into the current `/email` query, preserving extras such as `gmail_connected`. */
function mergeListSearchParams(
  current: URLSearchParams,
  folder: string,
  accountId: string,
  q: string
): URLSearchParams {
  const next = new URLSearchParams(current.toString());
  next.set("folder", folder);
  if (accountId && accountId !== "all") next.set("account", accountId);
  else next.delete("account");
  if (q) next.set("q", q);
  else next.delete("q");
  return next;
}

export interface InboxPanelProps {
  /**
   * The connected accounts, used to populate the account filter
   * dropdown. The parent page already fetches this list; passing it
   * down avoids a second `listEmailAccounts()` call.
   */
  accounts: EmailAccount[];
  /**
   * Callback so Reply/Forward can open the persistent compose modal with
   * a pre-fill, or the toolbar's "Nova mensagem" button can open it empty
   * (called with no argument).
   */
  onCompose?: (prefill?: ComposePrefill) => void;
}

export function InboxPanel({ accounts, onCompose }: InboxPanelProps) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const hasAccounts = accounts.length > 0;

  const [folder, setFolder] = useState<FolderName>(() =>
    folderFromSearch(searchParams.get("folder"))
  );
  const [customFolders, setCustomFolders] = useState<string[]>([]);
  const [accountId, setAccountId] = useState(
    () => searchParams.get("account") ?? "all"
  );
  const [offset, setOffset] = useState(0);

  const [emails, setEmails] = useState<Email[]>([]);
  const [total, setTotal] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const initialQ = searchParams.get("q")?.trim() ?? "";
  const [searchDraft, setSearchDraft] = useState(initialQ);
  const [searchQuery, setSearchQuery] = useState(initialQ);
  const [searchResults, setSearchResults] = useState<Email[] | null>(null);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);

  const loadEmails = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await listEmails({
        folder,
        account_id: accountId === "all" ? undefined : accountId,
        limit: PAGE_SIZE,
        offset,
      });
      setEmails(result);
      // Backend currently returns a plain array (no total/has_more).
      // We treat "less than PAGE_SIZE returned" as the last page.
      setTotal(result.length);
      // Discover any custom folders that surface in the current listing —
      // IMAP providers (Gmail labels, Outlook folders, ...) expose
      // arbitrary names and there's no dedicated folders endpoint in
      // this MVP.
      const custom = new Set<string>();
      for (const email of result) {
        if (!(STANDARD_FOLDERS as readonly string[]).includes(email.folder)) {
          custom.add(email.folder);
        }
      }
      setCustomFolders((prev) => {
        const next = new Set(prev);
        for (const c of custom) next.add(c);
        return Array.from(next).sort();
      });
    } catch (err) {
      setError(errMessage(err));
    } finally {
      setLoading(false);
    }
  }, [folder, accountId, offset]);

  // Reset paging whenever the filter changes (REQ-004:
  // moving the user to a different folder starts them on the first page).
  useEffect(() => {
    setOffset(0);
  }, [folder, accountId]);

  useEffect(() => {
    loadEmails();
  }, [loadEmails]);

  useEffect(() => {
    const next = mergeListSearchParams(
      new URLSearchParams(searchParams.toString()),
      folder,
      accountId,
      searchQuery
    );
    if (next.toString() === searchParams.toString()) return;
    const qs = next.toString();
    router.replace(qs ? `/email?${qs}` : "/email");
  }, [folder, accountId, searchQuery, router, searchParams]);

  // REQ-009: activating a row/card navigates to the reading page.
  const handleOpenEmail = useCallback(
    (email: Email) => {
      const params = new URLSearchParams();
      params.set("folder", folder);
      if (accountId !== "all") params.set("account", accountId);
      if (searchQuery) params.set("q", searchQuery);
      const qs = params.toString();
      router.push(qs ? `/email/${email.id}?${qs}` : `/email/${email.id}`);
    },
    [router, folder, accountId, searchQuery]
  );

  // Search -------------------------------------------------------------
  const searchAbortRef = useRef<AbortController | null>(null);
  const handleSearch = useCallback(async () => {
    const query = searchDraft.trim();
    if (!query) {
      setSearchQuery("");
      setSearchResults(null);
      setSearchError(null);
      return;
    }
    searchAbortRef.current?.abort();
    const controller = new AbortController();
    searchAbortRef.current = controller;
    setSearchQuery(query);
    setSearchLoading(true);
    setSearchError(null);
    try {
      const result = await searchEmails(query, {
        account_id: accountId === "all" ? undefined : accountId,
        limit: 50,
      });
      if (controller.signal.aborted) return;
      setSearchResults(result);
    } catch (err) {
      if (controller.signal.aborted) return;
      setSearchError(errMessage(err));
      setSearchResults([]);
    } finally {
      if (!controller.signal.aborted) setSearchLoading(false);
    }
  }, [searchDraft, accountId]);

  const hydratedSearch = useRef(false);
  useEffect(() => {
    if (hydratedSearch.current) return;
    if (!searchQuery) return;
    hydratedSearch.current = true;
    void handleSearch();
  }, [searchQuery, handleSearch]);

  const showSearchResults = searchResults !== null;
  const displayedEmails = showSearchResults ? searchResults ?? [] : emails;

  const allFolders = useMemo(
    () => [...STANDARD_FOLDERS, ...customFolders],
    [customFolders]
  );

  return (
    <div className="flex flex-col gap-4">
      {error && (
        <p
          className="text-sm text-destructive"
          role="alert"
        >
          {error}
        </p>
      )}

      <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
        <Select
          value={folder}
          onValueChange={(value) => setFolder(value as FolderName)}
        >
          <SelectTrigger
            className="w-48"
            aria-label="Pasta"
          >
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {allFolders.map((f) => (
              <SelectItem
                key={f}
                value={f}
              >
                {folderLabel(f)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select
          value={accountId}
          onValueChange={setAccountId}
        >
          <SelectTrigger
            className="w-64"
            aria-label="Conta"
          >
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Todas as contas</SelectItem>
            {accounts.map((a) => (
              <SelectItem
                key={a.id}
                value={a.id}
              >
                {a.display_name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <div className="flex min-w-0 flex-1 flex-wrap items-center gap-2">
          <Input
            placeholder="Buscar em remetente, assunto ou corpo…"
            value={searchDraft}
            onChange={(e) => setSearchDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") handleSearch();
            }}
            aria-label="Buscar e-mails"
            className="w-64 min-w-0"
          />
          <Button
            type="button"
            variant="secondary"
            onClick={handleSearch}
            disabled={searchLoading}
          >
            <Search className="mr-2 h-4 w-4" />
            Buscar
          </Button>
          {showSearchResults && (
            <Button
              type="button"
              variant="ghost"
              onClick={() => {
                setSearchDraft("");
                setSearchQuery("");
                setSearchResults(null);
                setSearchError(null);
              }}
            >
              Limpar busca
            </Button>
          )}
          <Button
            type="button"
            className="ml-auto w-full sm:w-auto"
            onClick={() => onCompose?.()}
            disabled={!hasAccounts}
            aria-label="Nova mensagem"
          >
            <Pencil className="mr-2 h-4 w-4" />
            Nova mensagem
          </Button>
        </div>
      </div>

      {!hasAccounts && (
        <p className="text-xs text-muted-foreground">
          Conecte uma conta na aba &quot;Contas&quot; para começar.
        </p>
      )}

      {searchError && (
        <p
          className="text-sm text-destructive"
          role="alert"
        >
          {searchError}
        </p>
      )}
      {showSearchResults && (
        <p className="text-xs text-muted-foreground">
          {searchLoading
            ? "Buscando…"
            : `${
                searchResults?.length ?? 0
              } resultado(s) para "${searchQuery}"`}
        </p>
      )}

      <div className="rounded-md border border-border">
        {loading ? (
          <div className="space-y-2 p-3">
            <Skeleton className="h-12 w-full" />
            <Skeleton className="h-12 w-full" />
            <Skeleton className="h-12 w-full" />
          </div>
        ) : displayedEmails.length === 0 ? (
          <div className="px-4 py-12 text-center text-sm text-muted-foreground">
            <Inbox
              className="mx-auto mb-2 h-8 w-8 opacity-50"
              aria-hidden="true"
            />
            {showSearchResults
              ? "Nenhum resultado."
              : "Nenhum e-mail nesta pasta."}
          </div>
        ) : (
          <>
            {/* Desktop table — email-inbox-responsiveness REQ-011:
                visible from the md breakpoint up. Below md the wrapper
                is `hidden` and the card list below takes over. */}
            <div className="hidden overflow-x-auto md:block">
              <table className="w-full text-sm">
                <thead className="border-b border-border bg-muted/40 text-left">
                  <tr>
                    <th className="px-3 py-2 font-medium">Status</th>
                    <th className="px-3 py-2 font-medium">Nome/e-mail</th>
                    <th className="px-3 py-2 font-medium">Assunto</th>
                    <th className="px-3 py-2 font-medium">Data</th>
                  </tr>
                </thead>
                <tbody>
                  {displayedEmails.map((email) => (
                    <tr
                      key={email.id}
                      className="cursor-pointer border-b border-border transition-colors last:border-0 hover:bg-accent"
                      onClick={() => handleOpenEmail(email)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          handleOpenEmail(email);
                        }
                      }}
                      tabIndex={0}
                      role="button"
                      aria-label={`E-mail de ${
                        email.from_name ?? email.from_address
                      }: ${email.subject ?? "(sem assunto)"}`}
                    >
                      <td className="px-3 py-2">
                        {email.is_read ? (
                          <MailOpen
                            className="h-4 w-4 text-muted-foreground"
                            role="img"
                            aria-label="Lido"
                          />
                        ) : (
                          <Mail
                            className="h-4 w-4"
                            role="img"
                            aria-label="Não lido"
                          />
                        )}
                      </td>
                      <td
                        className={`truncate px-3 py-2 ${
                          email.is_read
                            ? "font-normal text-muted-foreground"
                            : "font-semibold"
                        }`}
                      >
                        {email.from_name ?? email.from_address}
                      </td>
                      <td
                        className={`truncate px-3 py-2 ${
                          email.is_read
                            ? "text-muted-foreground"
                            : "font-medium"
                        }`}
                      >
                        {email.subject ?? "(sem assunto)"}
                        {email.has_attachments && (
                          <span
                            className="ml-1 text-xs text-muted-foreground"
                            aria-label="Possui anexos"
                          >
                            📎
                          </span>
                        )}
                      </td>
                      <td className="whitespace-nowrap px-3 py-2 text-xs text-muted-foreground">
                        {formatReceivedAt(email.received_at)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Mobile card list — email-inbox-responsiveness REQ-011:
                mirrors the desktop row's data points. Hidden on md+
                (table takes over). Keyboard activation and the
                per-card visual styling land in task-cards-1. */}
            <ul className="flex flex-col gap-3 p-3 md:hidden">
              {displayedEmails.map((email) => (
                <li
                  key={email.id}
                  data-testid="email-card"
                  role="button"
                  tabIndex={0}
                  aria-label={`Abrir e-mail de ${
                    email.from_name ?? email.from_address
                  }: ${email.subject ?? "(sem assunto)"}`}
                  onClick={() => handleOpenEmail(email)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      handleOpenEmail(email);
                    }
                  }}
                  className="flex cursor-pointer flex-col gap-1 rounded-md border border-border p-3 transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <div className="flex items-center gap-2">
                    {email.is_read ? (
                      <MailOpen
                        className="h-4 w-4 shrink-0 text-muted-foreground"
                        role="img"
                        aria-label="Lido"
                      />
                    ) : (
                      <Mail
                        className="h-4 w-4 shrink-0"
                        role="img"
                        aria-label="Não lido"
                      />
                    )}
                    <span
                      className={`truncate ${
                        email.is_read
                          ? "font-normal text-muted-foreground"
                          : "font-semibold"
                      }`}
                    >
                      {email.from_name ?? email.from_address}
                    </span>
                  </div>
                  <p
                    className={`line-clamp-2 ${
                      email.is_read ? "text-muted-foreground" : "font-medium"
                    }`}
                  >
                    {email.subject ?? "(sem assunto)"}
                    {email.has_attachments && (
                      <span
                        className="ml-1 text-xs text-muted-foreground"
                        aria-label="Possui anexos"
                      >
                        📎
                      </span>
                    )}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {formatReceivedAt(email.received_at)}
                  </p>
                </li>
              ))}
            </ul>
          </>
        )}

        {!showSearchResults && (
          <div className="flex items-center justify-between gap-2 border-t border-border px-3 py-2 text-xs text-muted-foreground">
            <span>
              {total !== null && total < PAGE_SIZE
                ? `Página ${
                    Math.floor(offset / PAGE_SIZE) + 1
                  } (${total} nesta página)`
                : `Página ${Math.floor(offset / PAGE_SIZE) + 1}`}
            </span>
            <div className="flex items-center gap-2">
              <Button
                type="button"
                variant="ghost"
                size="sm"
                disabled={offset === 0}
                onClick={() => setOffset((o) => Math.max(0, o - PAGE_SIZE))}
                aria-label="Página anterior"
              >
                <ChevronLeft className="h-4 w-4" />
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                disabled={total !== null && total < PAGE_SIZE}
                onClick={() => setOffset((o) => o + PAGE_SIZE)}
                aria-label="Próxima página"
              >
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
