"use client";

/**
 * Full-pane email reading chrome (email-detail-full-page REQ-009 / 010 / 015 / 017).
 *
 * Renders subject, icon actions with tooltips, From/To/Date metadata, and
 * the message body (`EmailHtmlBody` iframe or `<pre>` fallback). Root is a
 * `section` filling the app content pane (`h-[calc(100vh-4rem)]`), not a
 * `Dialog`. Reply/forward open a local `ComposeDialog`; move-folder is a
 * separate dialog. The `/email/[id]` page loads the message and passes
 * `email`, `error`, `listHref`, and `accounts`.
 */

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Archive, ChevronLeft, Mail, Send, Star, Trash2 } from "lucide-react";
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
import { TooltipIconButton } from "@/components/ui/tooltip-icon-button";
import { ApiError } from "@/lib/api";
import { updateEmail, type Email, type EmailAccount } from "@/lib/email";

import { ComposeDialog, type ComposePrefill } from "./ComposeDialog";
import { EmailHtmlBody } from "./EmailHtmlBody";

const STANDARD_FOLDERS = ["Inbox", "Sent", "Drafts", "Trash", "Spam"] as const;

function errMessage(err: unknown): string {
  return err instanceof ApiError ? err.message : "Falha inesperada";
}

function folderLabel(folder: string): string {
  const map: Record<(typeof STANDARD_FOLDERS)[number], string> = {
    Inbox: "Caixa de Entrada",
    Sent: "Enviados",
    Drafts: "Rascunhos",
    Trash: "Lixeira",
    Spam: "Spam",
  };
  if ((STANDARD_FOLDERS as readonly string[]).includes(folder)) {
    return map[folder as (typeof STANDARD_FOLDERS)[number]];
  }
  return folder;
}

function formatReceivedAt(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString();
}

export interface EmailReadViewProps {
  email: Email | null;
  error?: boolean;
  listHref: string;
  accounts?: EmailAccount[];
}

export function EmailReadView({
  email,
  error = false,
  listHref,
  accounts = [],
}: EmailReadViewProps) {
  const [current, setCurrent] = useState<Email | null>(email);
  const [composeOpen, setComposeOpen] = useState(false);
  const [composePrefill, setComposePrefill] = useState<ComposePrefill | null>(
    null
  );
  const [moveOpen, setMoveOpen] = useState(false);
  const [moveTargetFolder, setMoveTargetFolder] = useState("Archive");

  useEffect(() => {
    setCurrent(email);
  }, [email]);

  const showError = error || !current;

  const handleToggleRead = useCallback(async () => {
    if (!current) return;
    try {
      const updated = await updateEmail(current.id, {
        is_read: !current.is_read,
      });
      setCurrent(updated);
    } catch (err) {
      toast.error(errMessage(err));
    }
  }, [current]);

  const handleReply = useCallback(() => {
    if (!current) return;
    const subject = current.subject ?? "";
    const prefixed = subject.toLowerCase().startsWith("re:")
      ? subject
      : `Re: ${subject}`;
    const quoted = current.body_text ?? current.body_html ?? "";
    const prefill: ComposePrefill = {
      account_id: current.email_account_id,
      to_addresses: [current.from_address],
      subject: prefixed,
      body_text: quoted
        ? `\n\n--- Em ${formatReceivedAt(current.received_at)} ${
            current.from_name ?? current.from_address
          } escreveu ---\n${quoted}`
        : "",
      in_reply_to: current.message_id,
      references: current.thread_id ?? current.message_id,
    };
    setComposePrefill(prefill);
    setComposeOpen(true);
  }, [current]);

  const handleForward = useCallback(() => {
    if (!current) return;
    const subject = current.subject ?? "";
    const prefixed = subject.toLowerCase().startsWith("fwd:")
      ? subject
      : `Fwd: ${subject}`;
    const body = current.body_text ?? current.body_html ?? "";
    const prefill: ComposePrefill = {
      account_id: current.email_account_id,
      subject: prefixed,
      body_text: body
        ? `\n\n--- Mensagem encaminhada ---\nDe: ${
            current.from_name ?? current.from_address
          }\nPara: ${current.to_addresses.join(", ")}\nAssunto: ${
            current.subject ?? ""
          }\nData: ${formatReceivedAt(current.received_at)}\n\n${body}`
        : "",
    };
    setComposePrefill(prefill);
    setComposeOpen(true);
  }, [current]);

  const handleAskMove = useCallback(() => {
    if (!current) return;
    setMoveTargetFolder(current.folder === "Inbox" ? "Archive" : "Inbox");
    setMoveOpen(true);
  }, [current]);

  const handleConfirmMove = useCallback(async () => {
    if (!current) return;
    const destination = moveTargetFolder.trim();
    if (!destination) {
      toast.error("Pasta de destino inválida");
      return;
    }
    try {
      const updated = await updateEmail(current.id, { folder: destination });
      setCurrent(updated);
      setMoveOpen(false);
      toast.success(`Movido para ${folderLabel(destination)}`);
    } catch (err) {
      toast.error(errMessage(err));
    }
  }, [current, moveTargetFolder]);

  const handleDelete = useCallback(async () => {
    if (!current) return;
    try {
      const updated = await updateEmail(current.id, { folder: "Trash" });
      setCurrent(updated);
      toast.success("Movido para Lixeira");
    } catch (err) {
      toast.error(errMessage(err));
    }
  }, [current]);

  const folderSuggestions = [
    ...STANDARD_FOLDERS,
    ...(current &&
    !(STANDARD_FOLDERS as readonly string[]).includes(current.folder)
      ? [current.folder]
      : []),
  ];

  return (
    <section
      data-testid="email-read-view"
      className="flex h-[calc(100vh-4rem)] flex-col overflow-hidden bg-background"
    >
      <div
        data-testid="email-read-chrome"
        className="flex shrink-0 flex-col gap-3 border-b border-border px-6 py-4"
      >
        <Link
          href={listHref}
          className="inline-flex w-fit items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
        >
          <ChevronLeft className="h-4 w-4" />
          Voltar à caixa de entrada
        </Link>
        {showError ? (
          <p role="status">E-mail não encontrado</p>
        ) : (
          <>
            <h1 className="text-xl font-semibold">
              {current.subject ?? "(sem assunto)"}
            </h1>
            <div className="flex items-center gap-1">
              <TooltipIconButton
                icon={<Mail className="h-4 w-4" />}
                tooltip={
                  current.is_read ? "Marcar como não lido" : "Marcar como lido"
                }
                onClick={() => {
                  void handleToggleRead();
                }}
              />
              <TooltipIconButton
                icon={<Send className="h-4 w-4" />}
                tooltip="Responder"
                onClick={handleReply}
              />
              <TooltipIconButton
                icon={<Star className="h-4 w-4" />}
                tooltip="Encaminhar"
                onClick={handleForward}
              />
              <TooltipIconButton
                icon={<Archive className="h-4 w-4" />}
                tooltip="Mover para outra pasta"
                onClick={handleAskMove}
              />
              {current.folder !== "Trash" && (
                <TooltipIconButton
                  icon={<Trash2 className="h-4 w-4" />}
                  tooltip="Excluir (mover para lixeira)"
                  onClick={() => {
                    void handleDelete();
                  }}
                />
              )}
            </div>
            <dl className="grid gap-1 text-xs text-muted-foreground">
              <div className="flex flex-wrap items-center gap-x-2">
                <dt className="font-medium">De:</dt>
                <dd>
                  {current.from_name
                    ? `${current.from_name} <${current.from_address}>`
                    : current.from_address}
                </dd>
              </div>
              {current.to_addresses.length > 0 && (
                <div className="flex flex-wrap items-center gap-x-2">
                  <dt className="font-medium">Para:</dt>
                  <dd>{current.to_addresses.join(", ")}</dd>
                </div>
              )}
              {current.cc_addresses.length > 0 && (
                <div className="flex flex-wrap items-center gap-x-2">
                  <dt className="font-medium">Cc:</dt>
                  <dd>{current.cc_addresses.join(", ")}</dd>
                </div>
              )}
              <div className="flex flex-wrap items-center gap-x-2">
                <dt className="font-medium">Data:</dt>
                <dd>{formatReceivedAt(current.received_at)}</dd>
              </div>
              {current.contact_id && (
                <div className="flex flex-wrap items-center gap-x-2">
                  <dt className="font-medium">Contato:</dt>
                  <dd>vinculado (#{current.contact_id})</dd>
                </div>
              )}
            </dl>
          </>
        )}
      </div>
      <div
        data-testid="email-read-body"
        className="min-h-0 flex-1 overflow-hidden px-6 py-3"
      >
        {showError ? null : current.body_html ? (
          <EmailHtmlBody html={current.body_html} />
        ) : (
          <pre className="h-full overflow-auto whitespace-pre-wrap font-sans text-sm">
            {current.body_text ?? "(sem conteúdo)"}
          </pre>
        )}
      </div>

      <ComposeDialog
        open={composeOpen}
        onOpenChange={(open) => {
          setComposeOpen(open);
          if (!open) setComposePrefill(null);
        }}
        prefill={composePrefill}
        accounts={accounts}
      />

      <Dialog
        open={moveOpen}
        onOpenChange={setMoveOpen}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Mover e-mail</DialogTitle>
            <DialogDescription>Escolha a pasta de destino.</DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-2 py-2">
            <Label htmlFor="move-folder">Pasta de destino</Label>
            <Input
              id="move-folder"
              value={moveTargetFolder}
              onChange={(e) => setMoveTargetFolder(e.target.value)}
              list="email-read-folder-suggestions"
            />
            <datalist id="email-read-folder-suggestions">
              {folderSuggestions.map((folder) => (
                <option
                  key={folder}
                  value={folder}
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
              onClick={() => {
                void handleConfirmMove();
              }}
            >
              Mover
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </section>
  );
}
