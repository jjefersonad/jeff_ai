"use client";

/**
 * "Nova mensagem" modal (REQ-005 email-inbox; design Decision 7).
 *
 * Opened as a modal from:
 *   - the "Nova mensagem" button in `InboxPanel`'s toolbar, or
 *   - the Reply / Forward actions in `InboxPanel` (with a `prefill`).
 *
 * The dialog is the only compose entry point — composing is never a
 * standalone tab or route (design Decision 7). Closing the modal
 * without sending returns the user to whatever tab/folder they were
 * viewing unchanged: the page never tears down the inbox or accounts
 * state when this opens, and the `onOpenChange(false)` callback only
 * flips the open flag and clears the page-side `composePrefill`.
 *
 * Editor: Tiptap (per design's rich-text-editor choice). Starter kit
 * gives bold / italic / headings / bullet/ordered lists / blockquote /
 * code; the toolbar surfaces the most-used ones. A plain-text fallback
 * toggle hides the toolbar and replaces the editor with a `<textarea>`
 * for users who paste markdown or want a no-formatting draft.
 *
 * Send: calls `sendEmail(payload)` from `lib/email.ts`. The backend
 * SMTP dispatch is the same code path used by the agent's `send_email`
 * tool — only the agent path is wrapped by `interrupt_on` (Decision 6).
 * `body_text` is derived from the Tiptap doc's plain-text projection
 * so the receiving client always sees both representations.
 *
 * Attachment upload: not wired in this task — `lib/email.ts`'s
 * `SendEmailPayload` doesn't yet model attachments. The field is
 * reserved in the dialog so a follow-up task can plug it in without
 * touching the page or the dialog's public props.
 */

import { useEffect, useMemo, useState } from "react";
import {
  EditorContent,
  useEditor,
  type Editor as TiptapEditor,
} from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import {
  Bold,
  Italic,
  List as ListIcon,
  ListOrdered,
  Quote,
  Code,
  Heading1,
  Heading2,
  Send,
  Type,
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
import { Textarea } from "@/components/ui/textarea";
import { ApiError } from "@/lib/api";
import { sendEmail, type EmailAccount } from "@/lib/email";

export interface ComposePrefill {
  /** Sender account (the SMTP identity). Reply/Forward set this to the
   *  originating email's account so the reply lands in the same thread
   *  (REQ-005 email-inbox — thread_id is per-account). */
  account_id?: string;
  to_addresses?: string[];
  cc_addresses?: string[];
  bcc_addresses?: string[];
  subject?: string;
  /**
   * Initial body as plain text (used as the editor's source for new
   * / reply / forward pre-fills; the dialog converts each line to a
   * `<p>` so the editor starts with proper block structure).
   */
  body_text?: string;
  in_reply_to?: string;
  references?: string;
}

export interface ComposeDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Optional reply/forward pre-fill (wired by `InboxPanel`). */
  prefill?: ComposePrefill | null;
  /** Accounts the user can send from (typically the page passes its
   *  shared `accounts` list). */
  accounts: EmailAccount[];
}

function errMessage(err: unknown): string {
  return err instanceof ApiError ? err.message : "Falha inesperada";
}

/**
 * Parse a comma- or semicolon-separated address list into a clean
 * string array. Trims whitespace and drops empty entries.
 */
function parseAddresses(input: string): string[] {
  return input
    .split(/[,;]+/)
    .map((part) => part.trim())
    .filter((part) => part.length > 0);
}

/**
 * Convert plain text to a Tiptap-friendly HTML string (each non-empty
 * line wrapped in `<p>`, empty lines preserved as `<p><br></p>` so
 * paragraph spacing survives the editor's serialization).
 */
function plainTextToHtml(text: string): string {
  if (!text) return "";
  const lines = text.split(/\r?\n/);
  return lines
    .map((line) => {
      const escaped = line
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;");
      return line.length === 0 ? "<p><br></p>" : `<p>${escaped}</p>`;
    })
    .join("");
}

function ToolbarButton({
  active,
  onClick,
  ariaLabel,
  children,
  disabled,
}: {
  active?: boolean;
  onClick: () => void;
  ariaLabel: string;
  children: React.ReactNode;
  disabled?: boolean;
}) {
  return (
    <Button
      type="button"
      size="icon"
      variant={active ? "default" : "ghost"}
      onClick={onClick}
      aria-label={ariaLabel}
      aria-pressed={active}
      disabled={disabled}
      className="h-8 w-8"
    >
      {children}
    </Button>
  );
}

function EditorToolbar({ editor }: { editor: TiptapEditor | null }) {
  if (!editor) return null;
  return (
    <div
      className="flex flex-wrap items-center gap-1 border-b border-border p-1"
      role="toolbar"
      aria-label="Formatação do corpo do e-mail"
    >
      <ToolbarButton
        active={editor.isActive("bold")}
        onClick={() => editor.chain().focus().toggleBold().run()}
        ariaLabel="Negrito"
      >
        <Bold className="h-4 w-4" aria-hidden="true" />
      </ToolbarButton>
      <ToolbarButton
        active={editor.isActive("italic")}
        onClick={() => editor.chain().focus().toggleItalic().run()}
        ariaLabel="Itálico"
      >
        <Italic className="h-4 w-4" aria-hidden="true" />
      </ToolbarButton>
      <ToolbarButton
        active={editor.isActive("heading", { level: 1 })}
        onClick={() => editor.chain().focus().toggleHeading({ level: 1 }).run()}
        ariaLabel="Título 1"
      >
        <Heading1 className="h-4 w-4" aria-hidden="true" />
      </ToolbarButton>
      <ToolbarButton
        active={editor.isActive("heading", { level: 2 })}
        onClick={() => editor.chain().focus().toggleHeading({ level: 2 }).run()}
        ariaLabel="Título 2"
      >
        <Heading2 className="h-4 w-4" aria-hidden="true" />
      </ToolbarButton>
      <ToolbarButton
        active={editor.isActive("bulletList")}
        onClick={() => editor.chain().focus().toggleBulletList().run()}
        ariaLabel="Lista"
      >
        <ListIcon className="h-4 w-4" aria-hidden="true" />
      </ToolbarButton>
      <ToolbarButton
        active={editor.isActive("orderedList")}
        onClick={() => editor.chain().focus().toggleOrderedList().run()}
        ariaLabel="Lista numerada"
      >
        <ListOrdered className="h-4 w-4" aria-hidden="true" />
      </ToolbarButton>
      <ToolbarButton
        active={editor.isActive("blockquote")}
        onClick={() => editor.chain().focus().toggleBlockquote().run()}
        ariaLabel="Citação"
      >
        <Quote className="h-4 w-4" aria-hidden="true" />
      </ToolbarButton>
      <ToolbarButton
        active={editor.isActive("codeBlock")}
        onClick={() => editor.chain().focus().toggleCodeBlock().run()}
        ariaLabel="Bloco de código"
      >
        <Code className="h-4 w-4" aria-hidden="true" />
      </ToolbarButton>
    </div>
  );
}

export function ComposeDialog({
  open,
  onOpenChange,
  prefill,
  accounts,
}: ComposeDialogProps) {
  const [accountId, setAccountId] = useState<string>("");
  const [to, setTo] = useState("");
  const [cc, setCc] = useState("");
  const [bcc, setBcc] = useState("");
  const [subject, setSubject] = useState("");
  const [plainTextMode, setPlainTextMode] = useState(false);
  const [plainText, setPlainText] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const activeAccounts = useMemo(
    () => accounts.filter((a) => a.is_active),
    [accounts]
  );

  const initialHtml = useMemo(() => plainTextToHtml(prefill?.body_text ?? ""), [prefill]);

  const editor = useEditor({
    extensions: [StarterKit],
    content: initialHtml,
    editable: !sending,
    immediatelyRender: false,
    editorProps: {
      attributes: {
        class:
          "prose prose-sm max-w-none min-h-[200px] focus:outline-none px-3 py-2",
        "aria-label": "Corpo do e-mail",
      },
    },
  });

  // Reset state every time the dialog opens so the previous compose
  // doesn't leak into the next one (per task AC: closing it returns to
  // the prior view unchanged, and reopening starts a fresh draft).
  useEffect(() => {
    if (!open) return;
    setError(null);
    setSending(false);
    setAccountId(prefill?.account_id ?? activeAccounts[0]?.id ?? "");
    setTo((prefill?.to_addresses ?? []).join(", "));
    setCc((prefill?.cc_addresses ?? []).join(", "));
    setBcc((prefill?.bcc_addresses ?? []).join(", "));
    setSubject(prefill?.subject ?? "");
    const initialPlain = prefill?.body_text ?? "";
    setPlainText(initialPlain);
    setPlainTextMode(false);
  }, [open, prefill, activeAccounts]);

  // Push initial HTML into the editor whenever the prefill changes
  // (the editor instance is created once and reused).
  useEffect(() => {
    if (!editor || !open) return;
    editor.commands.setContent(initialHtml, false);
  }, [editor, initialHtml, open]);

  const handleSend = async () => {
    setError(null);
    if (!accountId) {
      setError("Selecione uma conta para enviar.");
      return;
    }
    const toAddresses = parseAddresses(to);
    if (toAddresses.length === 0) {
      setError("Informe ao menos um destinatário em \"Para\".");
      return;
    }

    let bodyHtml: string | null = null;
    let bodyText: string;
    if (plainTextMode) {
      bodyText = plainText;
    } else {
      bodyHtml = editor?.getHTML() ?? "";
      bodyText = editor?.getText() ?? "";
    }

    const trimmedSubject = subject.trim();

    setSending(true);
    try {
      await sendEmail({
        account_id: accountId,
        to_addresses: toAddresses,
        cc_addresses: parseAddresses(cc),
        bcc_addresses: parseAddresses(bcc),
        subject: trimmedSubject,
        body_text: bodyText,
        body_html: bodyHtml,
        in_reply_to: prefill?.in_reply_to ?? null,
        references: prefill?.references ?? null,
      });
      toast.success("E-mail enviado");
      onOpenChange(false);
    } catch (err) {
      setError(errMessage(err));
    } finally {
      setSending(false);
    }
  };

  const isReply = Boolean(prefill?.in_reply_to);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>
            {isReply ? "Responder" : prefill?.subject ? "Encaminhar" : "Nova mensagem"}
          </DialogTitle>
          <DialogDescription>
            {isReply
              ? `Respondendo: ${prefill?.subject ?? "(sem assunto)"}`
              : "Editor rich-text com fallback para texto puro. O envio usa SMTP da conta selecionada."}
          </DialogDescription>
        </DialogHeader>

        {activeAccounts.length === 0 ? (
          <div className="rounded-md border border-dashed border-border p-4 text-sm text-muted-foreground">
            Nenhuma conta ativa para envio. Conecte uma conta na aba
            &quot;Contas&quot; primeiro.
          </div>
        ) : (
          <div className="flex flex-col gap-3 py-2">
            <div className="flex flex-col gap-1">
              <Label htmlFor="compose-account">De (conta SMTP)</Label>
              <Select
                value={accountId}
                onValueChange={setAccountId}
                disabled={sending || isReply}
              >
                <SelectTrigger id="compose-account">
                  <SelectValue placeholder="Selecione uma conta" />
                </SelectTrigger>
                <SelectContent>
                  {activeAccounts.map((a) => (
                    <SelectItem key={a.id} value={a.id}>
                      {a.display_name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {isReply && (
                <p className="text-xs text-muted-foreground">
                  Conta fixada para preservar o thread_id do e-mail
                  original.
                </p>
              )}
            </div>

            <div className="flex flex-col gap-1">
              <Label htmlFor="compose-to">Para *</Label>
              <Input
                id="compose-to"
                placeholder="destinatario@exemplo.com, outro@exemplo.com"
                value={to}
                onChange={(e) => setTo(e.target.value)}
                disabled={sending}
              />
            </div>

            <details className="rounded-md border border-border p-2">
              <summary className="cursor-pointer text-sm text-muted-foreground">
                Cc / Bcc
              </summary>
              <div className="mt-2 flex flex-col gap-2">
                <div className="flex flex-col gap-1">
                  <Label htmlFor="compose-cc">Cc</Label>
                  <Input
                    id="compose-cc"
                    placeholder="copia@exemplo.com"
                    value={cc}
                    onChange={(e) => setCc(e.target.value)}
                    disabled={sending}
                  />
                </div>
                <div className="flex flex-col gap-1">
                  <Label htmlFor="compose-bcc">Bcc</Label>
                  <Input
                    id="compose-bcc"
                    placeholder="copia-oculta@exemplo.com"
                    value={bcc}
                    onChange={(e) => setBcc(e.target.value)}
                    disabled={sending}
                  />
                </div>
              </div>
            </details>

            <div className="flex flex-col gap-1">
              <Label htmlFor="compose-subject">Assunto</Label>
              <Input
                id="compose-subject"
                value={subject}
                onChange={(e) => setSubject(e.target.value)}
                disabled={sending}
              />
            </div>

            <div className="flex items-center justify-between">
              <Label>Corpo</Label>
              <Button
                type="button"
                size="sm"
                variant="ghost"
                onClick={() => {
                  if (plainTextMode) {
                    setPlainText(editor?.getText() ?? "");
                  } else {
                    setPlainText(editor?.getText() ?? "");
                  }
                  setPlainTextMode((v) => !v);
                }}
                disabled={sending}
                aria-pressed={plainTextMode}
              >
                <Type className="mr-2 h-4 w-4" />
                {plainTextMode ? "Voltar para rich-text" : "Texto puro"}
              </Button>
            </div>

            {plainTextMode ? (
              <Textarea
                value={plainText}
                onChange={(e) => setPlainText(e.target.value)}
                placeholder="Escreva a mensagem…"
                rows={10}
                disabled={sending}
                aria-label="Corpo do e-mail (texto puro)"
              />
            ) : (
              <div className="rounded-md border border-border bg-background">
                <EditorToolbar editor={editor} />
                <EditorContent editor={editor} />
              </div>
            )}

            {error && (
              <p className="text-sm text-destructive" role="alert">
                {error}
              </p>
            )}
          </div>
        )}

        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={sending}
          >
            Cancelar
          </Button>
          <Button
            type="button"
            onClick={handleSend}
            disabled={sending || activeAccounts.length === 0}
          >
            <Send className="mr-2 h-4 w-4" />
            {sending ? "Enviando..." : "Enviar"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
