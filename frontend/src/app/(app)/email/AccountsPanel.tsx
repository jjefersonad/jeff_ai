"use client";

/**
 * "Contas" tab panel for `/email` (REQ-001/002/004 email-account-management).
 *
 * Lists the authenticated user's connected IMAP/SMTP accounts (backend
 * already scopes by `user_id` — REQ-002 needs no client-side filtering),
 * with Edit (toggle `is_active`/`display_name` via `updateEmailAccount`)
 * and Remove (`deleteEmailAccount`) actions. The connect dialog lives in
 * `ConnectAccountDialog.tsx` and is opened from the header's "Adicionar"
 * button.
 *
 * Mirrors the desktop table / mobile card pattern used by
 * `app/(app)/integrations/page.tsx` and `ContactsPanel.tsx`.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { Pencil, Plus, Settings, Trash2 } from "lucide-react";
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
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { ApiError } from "@/lib/api";
import {
  connectEmailAccount,
  deleteEmailAccount,
  listEmailAccounts,
  updateEmailAccount,
  type EmailAccount,
  type EmailAccountConnectPayload,
} from "@/lib/email";

import { ConnectAccountDialog } from "./ConnectAccountDialog";

function errMessage(err: unknown): string {
  return err instanceof ApiError ? err.message : "Falha inesperada";
}

export interface AccountsPanelProps {
  /**
   * Notify the parent page so it can refresh shared state (e.g. the
   * Caixa de Entrada view) when accounts change.
   */
  onAccountsChanged?: () => void;
}

export function AccountsPanel({ onAccountsChanged }: AccountsPanelProps) {
  const [accounts, setAccounts] = useState<EmailAccount[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [connectOpen, setConnectOpen] = useState(false);

  const [editing, setEditing] = useState<EmailAccount | null>(null);
  const [editDisplayName, setEditDisplayName] = useState("");
  const [editIsActive, setEditIsActive] = useState(true);
  const [editSaving, setEditSaving] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);

  // Estado do diálogo "Editar conexão" — reutiliza o `ConnectAccountDialog`
  // em `mode="edit"` para editar host/porta/usuário/senha IMAP/SMTP.
  // `connectionEditing` é a conta-alvo; o dialog faz o fetch dos
  // valores via `prefill` (vem da resposta de `listEmailAccounts`).
  const [connectionEditing, setConnectionEditing] =
    useState<EmailAccount | null>(null);

  const [deleteTarget, setDeleteTarget] = useState<EmailAccount | null>(null);
  const [deleting, setDeleting] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const list = await listEmailAccounts();
      setAccounts(list);
    } catch (err) {
      setError(errMessage(err));
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const handleConnect = async (payload: EmailAccountConnectPayload) => {
    const created = await connectEmailAccount(payload);
    setAccounts((prev) => (prev ? [created, ...prev] : [created]));
    toast.success("Conta conectada");
    onAccountsChanged?.();
  };

  const openEdit = (account: EmailAccount) => {
    setEditing(account);
    setEditDisplayName(account.display_name);
    setEditIsActive(account.is_active);
    setEditError(null);
  };

  const closeEdit = () => {
    setEditing(null);
    setEditError(null);
  };

  const handleSaveEdit = async () => {
    if (!editing) return;
    setEditError(null);
    if (!editDisplayName.trim()) {
      setEditError("Nome de exibição é obrigatório.");
      return;
    }
    setEditSaving(true);
    try {
      const updated = await updateEmailAccount(editing.id, {
        display_name: editDisplayName.trim(),
        is_active: editIsActive,
      });
      setAccounts((prev) =>
        prev
          ? prev.map((a) => (a.id === updated.id ? updated : a))
          : prev
      );
      toast.success("Conta atualizada");
      onAccountsChanged?.();
      closeEdit();
    } catch (err) {
      setEditError(errMessage(err));
    } finally {
      setEditSaving(false);
    }
  };

  const handleConfirmDelete = async () => {
    if (!deleteTarget || deleting) return;
    setDeleting(true);
    try {
      await deleteEmailAccount(deleteTarget.id);
      setAccounts((prev) =>
        prev ? prev.filter((a) => a.id !== deleteTarget.id) : prev
      );
      toast.success("Conta removida");
      onAccountsChanged?.();
      setDeleteTarget(null);
    } catch (err) {
      toast.error(errMessage(err));
    } finally {
      setDeleting(false);
    }
  };

  // O `ConnectAccountDialog` em modo `edit` recebe `prefill` com os
  // valores não-secretos da configuração; o backend os devolve em
  // `EmailAccountResponse` (REQ-002 email-account-edit-connection). Se
  // algum campo estiver ausente (resposta legada, conta em estado
  // intermediário), o `prefill` simplesmente omite o campo — o dialog
  // cai para os defaults ("993" / "587" / vazio), o que é equivalente
  // a um edit de campos vazios.
  const connectionPrefill = useMemo(
    () =>
      connectionEditing
        ? {
            imap_host: connectionEditing.imap_host ?? undefined,
            imap_port: connectionEditing.imap_port ?? undefined,
            imap_username: connectionEditing.imap_username ?? undefined,
            smtp_host: connectionEditing.smtp_host ?? undefined,
            smtp_port: connectionEditing.smtp_port ?? undefined,
            smtp_username: connectionEditing.smtp_username ?? undefined,
          }
        : undefined,
    [connectionEditing]
  );

  const handleConnectionEdited = (updated: EmailAccount) => {
    setAccounts((prev) =>
      prev ? prev.map((a) => (a.id === updated.id ? updated : a)) : prev
    );
    onAccountsChanged?.();
  };

  return (
    <div className="flex flex-col gap-4">
      {error && (
        <p className="text-sm text-destructive" role="alert">
          {error}
        </p>
      )}

      <div className="flex items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground">
          Conecte uma conta IMAP/SMTP para começar a receber e enviar
          e-mails. As credenciais são criptografadas por campo e nunca
          são devolvidas pela API.
        </p>
        <Button type="button" onClick={() => setConnectOpen(true)}>
          <Plus className="mr-2 h-4 w-4" />
          Conectar conta
        </Button>
      </div>

      {accounts === null && (
        <div className="space-y-3">
          <Skeleton className="h-14 w-full" />
          <Skeleton className="h-14 w-full" />
        </div>
      )}

      {accounts && accounts.length === 0 && (
        <div className="rounded-md border border-dashed border-border py-16 text-center text-muted-foreground">
          <p>Você ainda não tem contas de e-mail conectadas.</p>
        </div>
      )}

      {accounts && accounts.length > 0 && (
        <>
          {/* Desktop table */}
          <div className="hidden overflow-x-auto rounded-md border border-border md:block">
            <table className="w-full text-sm">
              <thead className="border-b border-border bg-muted/40 text-left">
                <tr>
                  <th className="px-3 py-2 font-medium">Conta</th>
                  <th className="px-3 py-2 font-medium">Status</th>
                  <th className="px-3 py-2 font-medium">Última sincronização</th>
                  <th className="px-3 py-2 font-medium">Ativa</th>
                  <th className="px-3 py-2 font-medium">Ações</th>
                </tr>
              </thead>
              <tbody>
                {accounts.map((account) => (
                  <tr
                    key={account.id}
                    className="border-b border-border last:border-0"
                  >
                    <td className="px-3 py-2">
                      <span className="font-medium">
                        {account.display_name}
                      </span>
                      <span className="mt-1 block text-xs text-muted-foreground">
                        {account.provider}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-muted-foreground">
                      {account.status}
                    </td>
                    <td className="px-3 py-2 text-muted-foreground">
                      {account.last_synced_at
                        ? new Date(account.last_synced_at).toLocaleString()
                        : "—"}
                    </td>
                    <td className="px-3 py-2 text-muted-foreground">
                      {account.is_active ? "Sim" : "Não"}
                    </td>
                    <td className="px-3 py-2">
                      <div className="flex gap-1">
                        <Button
                          type="button"
                          size="icon"
                          variant="ghost"
                          aria-label={`Editar ${account.display_name}`}
                          onClick={() => openEdit(account)}
                        >
                          <Pencil className="size-4" />
                        </Button>
                        <Button
                          type="button"
                          size="icon"
                          variant="ghost"
                          aria-label={`Editar conexão ${account.display_name}`}
                          onClick={() => setConnectionEditing(account)}
                        >
                          <Settings className="size-4" />
                        </Button>
                        <Button
                          type="button"
                          size="icon"
                          variant="ghost"
                          aria-label={`Remover ${account.display_name}`}
                          onClick={() => setDeleteTarget(account)}
                        >
                          <Trash2 className="size-4" />
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Mobile cards */}
          <ul className="flex flex-col gap-3 md:hidden">
            {accounts.map((account) => (
              <li
                key={account.id}
                className="rounded-md border border-border p-3"
              >
                <div className="flex items-center justify-between gap-2">
                  <div>
                    <span className="font-medium">{account.display_name}</span>
                    <span className="mt-1 block text-xs text-muted-foreground">
                      {account.provider} · {account.status}
                    </span>
                  </div>
                  <span className="text-xs text-muted-foreground">
                    {account.is_active ? "Ativa" : "Inativa"}
                  </span>
                </div>
                <p className="mt-1 text-xs text-muted-foreground">
                  Sincronizada{" "}
                  {account.last_synced_at
                    ? new Date(account.last_synced_at).toLocaleString()
                    : "nunca"}
                </p>
                <div className="mt-2 flex flex-wrap gap-2">
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    onClick={() => openEdit(account)}
                  >
                    Editar
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    onClick={() => setConnectionEditing(account)}
                  >
                    Editar conexão
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    onClick={() => setDeleteTarget(account)}
                  >
                    Remover
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        </>
      )}

      <ConnectAccountDialog
        open={connectOpen}
        onOpenChange={setConnectOpen}
        onSubmit={handleConnect}
      />

      {/* Edit-connection dialog (reuses ConnectAccountDialog in mode=edit). */}
      <ConnectAccountDialog
        open={connectionEditing != null}
        onOpenChange={(open) => {
          if (!open) setConnectionEditing(null);
        }}
        mode="edit"
        accountId={connectionEditing?.id}
        prefill={connectionPrefill}
        prefillDisplayName={connectionEditing?.display_name ?? ""}
        onAccountsChanged={handleConnectionEdited}
      />

      {/* Edit dialog */}
      <Dialog
        open={editing != null}
        onOpenChange={(open) => {
          if (!open) closeEdit();
        }}
      >
        <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Editar conta</DialogTitle>
            <DialogDescription>
              Atualize o nome de exibição ou desative a sincronização. Para
              trocar host/porta/usuário/senha IMAP/SMTP, use o botão
              &quot;Editar conexão&quot; na linha da conta.
            </DialogDescription>
          </DialogHeader>
          {editing && (
            <div className="flex flex-col gap-3">
              <div className="grid gap-1">
                <Label htmlFor="account-edit-name">Nome de exibição *</Label>
                <Input
                  id="account-edit-name"
                  value={editDisplayName}
                  onChange={(e) => setEditDisplayName(e.target.value)}
                />
              </div>
              <div className="flex items-center justify-between rounded-md border border-border p-3">
                <div className="flex flex-col">
                  <Label htmlFor="account-edit-active">Conta ativa</Label>
                  <span className="text-xs text-muted-foreground">
                    Quando inativa, o sync worker não conecta nesta conta.
                  </span>
                </div>
                <Switch
                  id="account-edit-active"
                  checked={editIsActive}
                  onCheckedChange={setEditIsActive}
                />
              </div>
              {editError && (
                <p className="text-sm text-destructive" role="alert">
                  {editError}
                </p>
              )}
            </div>
          )}
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={closeEdit}
              disabled={editSaving}
            >
              Cancelar
            </Button>
            <Button type="button" onClick={handleSaveEdit} disabled={editSaving}>
              {editSaving ? "Salvando..." : "Salvar"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete confirmation */}
      <Dialog
        open={deleteTarget != null}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Remover conta?</DialogTitle>
            <DialogDescription>
              {deleteTarget
                ? `Isso remove a conta "${deleteTarget.display_name}" e suas credenciais IMAP/SMTP criptografadas. As mensagens já sincronizadas permanecem acessíveis — apenas a sincronização futura é interrompida.`
                : ""}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => setDeleteTarget(null)}
              disabled={deleting}
            >
              Cancelar
            </Button>
            <Button
              type="button"
              variant="destructive"
              onClick={handleConfirmDelete}
              disabled={deleting}
            >
              {deleting ? "Removendo..." : "Remover"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
