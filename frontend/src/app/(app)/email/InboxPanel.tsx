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
 *   - detail modal that calls `getEmail` (sanitized HTML — design
 *     Decision 3, `nh3` at ingest; the API never returns unsanitized
 *     HTML, so a direct `dangerouslySetInnerHTML` is the documented
 *     trust boundary) and closes by clearing the selection;
 *   - mark read/unread + move folder via `updateEmail`;
 *   - search via `searchEmails` (REQs REQ-003 + REQ-002 of inbox).
 *
 * Mirrors the CRM's hand-rolled `<table>` pattern (design note: no
 * data-table library added). Reply/Forward buttons render `ComposeDialog`
 * with a pre-fill owned by `task-frontend-4`; this panel only surfaces the
 * action stubs.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Archive,
  ChevronLeft,
  ChevronRight,
  Inbox,
  Mail,
  MailOpen,
  Pencil,
  Search,
  Send,
  Star,
  Trash2,
} from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { TooltipIconButton } from "@/components/ui/tooltip-icon-button";
import { ApiError } from "@/lib/api";
import {
  getEmail,
  listEmails,
  searchEmails,
  updateEmail,
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
  const hasAccounts = accounts.length > 0;

  const [folder, setFolder] = useState<FolderName>("Inbox");
  const [customFolders, setCustomFolders] = useState<string[]>([]);
  const [accountId, setAccountId] = useState<string>("all");
  const [offset, setOffset] = useState(0);

  const [emails, setEmails] = useState<Email[]>([]);
  const [total, setTotal] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedDetail, setSelectedDetail] = useState<Email | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const [searchDraft, setSearchDraft] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<Email[] | null>(null);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);

  const [moveOpen, setMoveOpen] = useState(false);
  const [moveTargetFolder, setMoveTargetFolder] = useState("Archive");

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

  // Reset paging + selection whenever the filter changes (REQ-004:
  // moving the user to a different folder starts them on the first page).
  useEffect(() => {
    setOffset(0);
    setSelectedId(null);
    setSelectedDetail(null);
  }, [folder, accountId]);

  useEffect(() => {
    loadEmails();
  }, [loadEmails]);

  // REQ-002: selecting an email loads the full body (which marks it
  // read server-side per the spec) and shows it in the detail modal.
  const handleSelectEmail = useCallback(async (email: Email) => {
    setSelectedId(email.id);
    setSelectedDetail(null);
    setDetailLoading(true);
    try {
      const fresh = await getEmail(email.id);
      setSelectedDetail(fresh);
      // Optimistically reflect the read state in the list — the backend
      // already flipped `is_read=true`, but the cached row in `emails`
      // still shows `is_read=false` until the next list refresh.
      setEmails((prev) =>
        prev.map((e) =>
          e.id === fresh.id ? { ...e, is_read: fresh.is_read } : e
        )
      );
    } catch (err) {
      setError(errMessage(err));
      setSelectedId(null);
    } finally {
      setDetailLoading(false);
    }
  }, []);

  const handleToggleRead = useCallback(
    async (email: Email) => {
      try {
        const updated = await updateEmail(email.id, {
          is_read: !email.is_read,
        });
        setEmails((prev) =>
          prev.map((e) => (e.id === updated.id ? updated : e))
        );
        if (selectedDetail?.id === updated.id) {
          setSelectedDetail(updated);
        }
      } catch (err) {
        toast.error(errMessage(err));
      }
    },
    [selectedDetail]
  );

  const handleAskMove = useCallback(() => {
    if (!selectedDetail) return;
    setMoveTargetFolder(
      selectedDetail.folder === "Inbox" ? "Archive" : "Inbox"
    );
    setMoveOpen(true);
  }, [selectedDetail]);

  const handleConfirmMove = useCallback(async () => {
    if (!selectedDetail) return;
    const destination = moveTargetFolder.trim();
    if (!destination) {
      toast.error("Pasta de destino inválida");
      return;
    }
    try {
      const updated = await updateEmail(selectedDetail.id, {
        folder: destination,
      });
      // REQ-004 / task acceptance: if the user is viewing the destination
      // folder the move should be reflected immediately; if they're
      // viewing the source folder the email should disappear from view.
      setEmails((prev) =>
        destination === folder
          ? [...prev, updated]
          : prev.filter((e) => e.id !== updated.id)
      );
      setSelectedDetail(updated);
      setSelectedId(null);
      setMoveOpen(false);
      toast.success(`Movido para ${folderLabel(destination)}`);
    } catch (err) {
      toast.error(errMessage(err));
    }
  }, [selectedDetail, moveTargetFolder, folder]);

  const handleDelete = useCallback(async () => {
    if (!selectedDetail) return;
    try {
      const updated = await updateEmail(selectedDetail.id, { folder: "Trash" });
      setEmails((prev) =>
        folder === "Trash"
          ? prev.map((e) => (e.id === updated.id ? updated : e))
          : prev.filter((e) => e.id !== updated.id)
      );
      setSelectedDetail(updated);
      setSelectedId(null);
      toast.success("Movido para Lixeira");
    } catch (err) {
      toast.error(errMessage(err));
    }
  }, [selectedDetail, folder]);

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

  const showSearchResults = searchResults !== null;
  const displayedEmails = showSearchResults ? searchResults ?? [] : emails;

  // Compose actions (Reply / Forward) ---------------------------------
  const handleReply = useCallback(
    (email: Email) => {
      const subject = email.subject ?? "";
      const prefixed = subject.toLowerCase().startsWith("re:")
        ? subject
        : `Re: ${subject}`;
      const quoted = email.body_text ?? email.body_html ?? "";
      const prefill: ComposePrefill = {
        account_id: email.email_account_id,
        to_addresses: [email.from_address],
        subject: prefixed,
        body_text: quoted
          ? `\n\n--- Em ${formatReceivedAt(email.received_at)} ${
              email.from_name ?? email.from_address
            } escreveu ---\n${quoted}`
          : "",
        in_reply_to: email.message_id,
        references: email.thread_id ?? email.message_id,
      };
      onCompose?.(prefill);
    },
    [onCompose]
  );

  const handleForward = useCallback(
    (email: Email) => {
      const subject = email.subject ?? "";
      const prefixed = subject.toLowerCase().startsWith("fwd:")
        ? subject
        : `Fwd: ${subject}`;
      const body = email.body_text ?? email.body_html ?? "";
      const prefill: ComposePrefill = {
        account_id: email.email_account_id,
        subject: prefixed,
        body_text: body
          ? `\n\n--- Mensagem encaminhada ---\nDe: ${
              email.from_name ?? email.from_address
            }\nPara: ${email.to_addresses.join(", ")}\nAssunto: ${
              email.subject ?? ""
            }\nData: ${formatReceivedAt(email.received_at)}\n\n${body}`
          : "",
      };
      onCompose?.(prefill);
    },
    [onCompose]
  );

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

        <div className="flex flex-1 flex-wrap items-center gap-2 min-w-0">
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
                      className={`cursor-pointer border-b border-border transition-colors last:border-0 hover:bg-accent ${
                        selectedId === email.id ? "bg-accent" : ""
                      }`}
                      onClick={() => handleSelectEmail(email)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          handleSelectEmail(email);
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
                  onClick={() => handleSelectEmail(email)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      handleSelectEmail(email);
                    }
                  }}
                  className={`flex cursor-pointer flex-col gap-1 rounded-md border border-border p-3 transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
                    selectedId === email.id ? "bg-accent" : ""
                  }`}
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

      {/* Detail dialog — REQ-009: full email detail opens as a modal;
          closing it clears the selection so no row stays marked selected. */}
      <Dialog
        open={!!selectedId}
        onOpenChange={(open) => {
          if (!open) {
            setSelectedId(null);
            setSelectedDetail(null);
          }
        }}
      >
        <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>
              {selectedDetail?.subject ??
                (detailLoading ? "Carregando…" : "(sem assunto)")}
            </DialogTitle>
            <DialogDescription className="sr-only">
              Detalhes do e-mail
              {selectedDetail
                ? ` de ${
                    selectedDetail.from_name ?? selectedDetail.from_address
                  }`
                : ""}
            </DialogDescription>
          </DialogHeader>
          {detailLoading && (
            <div className="space-y-2">
              <Skeleton className="h-4 w-1/2" />
              <Skeleton className="h-32 w-full" />
            </div>
          )}
          {selectedDetail && !detailLoading && (
            <>
              <div className="flex items-center gap-1">
                <TooltipIconButton
                  icon={<Mail className="h-4 w-4" />}
                  tooltip={
                    selectedDetail.is_read
                      ? "Marcar como não lido"
                      : "Marcar como lido"
                  }
                  onClick={() => handleToggleRead(selectedDetail)}
                />
                <TooltipIconButton
                  icon={<Send className="h-4 w-4" />}
                  tooltip="Responder"
                  onClick={() => handleReply(selectedDetail)}
                />
                <TooltipIconButton
                  icon={<Star className="h-4 w-4" />}
                  tooltip="Encaminhar"
                  onClick={() => handleForward(selectedDetail)}
                />
                <TooltipIconButton
                  icon={<Archive className="h-4 w-4" />}
                  tooltip="Mover para outra pasta"
                  onClick={handleAskMove}
                />
                {selectedDetail.folder !== "Trash" && (
                  <TooltipIconButton
                    icon={<Trash2 className="h-4 w-4" />}
                    tooltip="Excluir (mover para lixeira)"
                    onClick={handleDelete}
                  />
                )}
              </div>
              <dl className="grid gap-1 text-xs text-muted-foreground">
                <div className="flex flex-wrap items-center gap-x-2">
                  <dt className="font-medium">De:</dt>
                  <dd>
                    {selectedDetail.from_name
                      ? `${selectedDetail.from_name} <${selectedDetail.from_address}>`
                      : selectedDetail.from_address}
                  </dd>
                </div>
                {selectedDetail.to_addresses.length > 0 && (
                  <div className="flex flex-wrap items-center gap-x-2">
                    <dt className="font-medium">Para:</dt>
                    <dd>{selectedDetail.to_addresses.join(", ")}</dd>
                  </div>
                )}
                {selectedDetail.cc_addresses.length > 0 && (
                  <div className="flex flex-wrap items-center gap-x-2">
                    <dt className="font-medium">Cc:</dt>
                    <dd>{selectedDetail.cc_addresses.join(", ")}</dd>
                  </div>
                )}
                <div className="flex flex-wrap items-center gap-x-2">
                  <dt className="font-medium">Data:</dt>
                  <dd>{formatReceivedAt(selectedDetail.received_at)}</dd>
                </div>
                {selectedDetail.contact_id && (
                  <div className="flex flex-wrap items-center gap-x-2">
                    <dt className="font-medium">Contato:</dt>
                    <dd>vinculado (#{selectedDetail.contact_id})</dd>
                  </div>
                )}
              </dl>
              <div className="prose prose-sm max-w-none border-t border-border pt-3">
                {selectedDetail.body_html ? (
                  // The backend sanitizes `body_html` once at ingest with
                  // `nh3` (design Decision 3); the value returned here is
                  // the same already-sanitized string the agent's
                  // `read_email` tool sees. There is no client-side
                  // re-sanitization step — `nh3` runs server-side and the
                  // API never returns unsanitized HTML.
                  <div
                    dangerouslySetInnerHTML={{
                      __html: selectedDetail.body_html,
                    }}
                  />
                ) : (
                  <pre className="whitespace-pre-wrap font-sans text-sm">
                    {selectedDetail.body_text ?? "(sem conteúdo)"}
                  </pre>
                )}
              </div>
            </>
          )}
        </DialogContent>
      </Dialog>

      {/* Move-to dialog */}
      <Dialog
        open={moveOpen}
        onOpenChange={setMoveOpen}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Mover e-mail</DialogTitle>
            <DialogDescription>
              Escolha a pasta de destino. O e-mail será re-renderizado
              imediatamente na lista correspondente.
            </DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-2 py-2">
            <Label htmlFor="move-folder">Pasta de destino</Label>
            <Input
              id="move-folder"
              value={moveTargetFolder}
              onChange={(e) => setMoveTargetFolder(e.target.value)}
              list="folder-suggestions"
            />
            <datalist id="folder-suggestions">
              {allFolders.map((f) => (
                <option
                  key={f}
                  value={f}
                />
              ))}
            </datalist>
          </div>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => setMoveOpen(false)}
            >
              Cancelar
            </Button>
            <Button
              type="button"
              onClick={handleConfirmMove}
            >
              Mover
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
