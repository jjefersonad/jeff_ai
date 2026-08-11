"use client";

/**
 * Modal de "conectar / editar conexão de" uma conta de e-mail
 * IMAP/SMTP. Suporta dois modos (REQ-001 + REQ-002 do spec
 * `email-account-edit-connection`):
 *
 * - `mode="create"` (default): usado pelo botão "Adicionar conta"
 *   da `AccountsPanel`. Senhas são obrigatórias (validação existente).
 *   O submit chama `onSubmit(payload)` (handler do pai chama
 *   `connectEmailAccount(payload)`).
 *
 * - `mode="edit"`: usado pelo botão "Editar conexão" (próxima task,
 *   `frontend-ui-1`). O form é prefillado com os valores atuais de
 *   IMAP/SMTP; ambos os campos de senha ficam vazios com helper text
 *   "Deixe em branco para manter a senha atual". O submit chama o
 *   client `updateEmailAccountConfig(accountId, payload)` (PATCH) e
 *   invoca `onAccountsChanged(updated)` para que o pai atualize a
 *   linha correspondente na lista local sem refetch.
 *
 * Conjunto de campos, validação, labels e renderização de erro são
 * idênticos entre os dois modos — só diferem: defaults iniciais,
 * helper text sob as senhas, e o client chamado no submit.
 */

import { useEffect, useState } from "react";
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
import { ApiError } from "@/lib/api";
import {
  type EmailAccountConnectPayload,
  updateEmailAccountConfig,
} from "@/lib/email";

interface ConnectAccountDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /**
   * Usado apenas em `mode="create"`. O pai (`AccountsPanel`) recebe o
   * payload e chama `connectEmailAccount`.
   */
  onSubmit?: (payload: EmailAccountConnectPayload) => Promise<void>;
  /**
   * Modo do diálogo. Default = `"create"` (preserva o comportamento
   * pré-existente para todos os call sites atuais).
   */
  mode?: "create" | "edit";
  /**
   * `id` da conta sendo editada. Obrigatório em `mode="edit"`,
   * ignorado em `mode="create"`.
   */
  accountId?: string;
  /**
   * Valores iniciais dos campos IMAP/SMTP em `mode="edit"`. Campos
   * ausentes caem para os defaults do form. O componente NÃO busca
   * esses valores — o pai passa o que já tem.
   */
  prefill?: {
    imap_host?: string;
    imap_port?: number;
    imap_username?: string;
    smtp_host?: string;
    smtp_port?: number;
    smtp_username?: string | null;
  };
  /**
   * Valor inicial do campo "Nome de exibição" em `mode="edit"`.
   * Fornecido como prop separada para manter o tipo de `prefill`
   * estritamente ligado aos campos de configuração (não de metadata).
   */
  prefillDisplayName?: string;
  /**
   * Notifica o pai (`AccountsPanel`) para invalidar a lista de contas
   * após um save bem-sucedido em `mode="edit"`. Recebe a conta
   * atualizada retornada pelo backend para que o pai possa atualizar
   * o item da lista localmente (sem precisar de refetch).
   * Sem efeito em `mode="create"`.
   */
  onAccountsChanged?: (updated: import("@/lib/email").EmailAccount) => void;
}

interface FormState {
  display_name: string;
  imap_host: string;
  imap_port: string;
  imap_username: string;
  imap_password: string;
  smtp_host: string;
  smtp_port: string;
  smtp_username: string;
  smtp_password: string;
}

const emptyForm = (): FormState => ({
  display_name: "",
  imap_host: "",
  imap_port: "993",
  imap_username: "",
  imap_password: "",
  smtp_host: "",
  smtp_port: "587",
  smtp_username: "",
  smtp_password: "",
});

const prefillToForm = (
  displayName: string,
  prefill: ConnectAccountDialogProps["prefill"]
): FormState => ({
  display_name: displayName,
  imap_host: prefill?.imap_host ?? "",
  imap_port: prefill?.imap_port != null ? String(prefill.imap_port) : "993",
  imap_username: prefill?.imap_username ?? "",
  imap_password: "",
  smtp_host: prefill?.smtp_host ?? "",
  smtp_port: prefill?.smtp_port != null ? String(prefill.smtp_port) : "587",
  smtp_username: prefill?.smtp_username ?? "",
  smtp_password: "",
});

export function ConnectAccountDialog({
  open,
  onOpenChange,
  onSubmit,
  mode = "create",
  accountId,
  prefill,
  prefillDisplayName = "",
  onAccountsChanged,
}: ConnectAccountDialogProps) {
  const [form, setForm] = useState<FormState>(emptyForm);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      if (mode === "edit") {
        setForm(prefillToForm(prefillDisplayName, prefill));
      } else {
        setForm(emptyForm());
      }
      setError(null);
      setSaving(false);
    }
  }, [open, mode, prefill, prefillDisplayName]);

  const handleSubmit = async () => {
    setError(null);

    if (mode === "edit") {
      // Em modo edit a senha pode ficar vazia (= manter). Demais campos
      // são validados localmente: o backend re-valida via Pydantic de
      // qualquer forma, mas a validação local evita um round-trip
      // óbvio para typos.
      if (!form.display_name.trim()) {
        setError("Nome de exibição é obrigatório.");
        return;
      }
      if (!form.imap_host.trim() || !form.imap_username.trim()) {
        setError("Host e usuário IMAP são obrigatórios.");
        return;
      }
      const imapPort = Number(form.imap_port);
      if (!Number.isFinite(imapPort) || imapPort <= 0 || imapPort > 65535) {
        setError("Porta IMAP inválida.");
        return;
      }
      if (!form.smtp_host.trim()) {
        setError("Host SMTP é obrigatório.");
        return;
      }
      const smtpPort = Number(form.smtp_port);
      if (!Number.isFinite(smtpPort) || smtpPort <= 0 || smtpPort > 65535) {
        setError("Porta SMTP inválida.");
        return;
      }
      if (!accountId) {
        setError("ID da conta ausente — não é possível salvar.");
        return;
      }
      setSaving(true);
      try {
        const updated = await updateEmailAccountConfig(accountId, {
          display_name: form.display_name.trim(),
          imap_host: form.imap_host.trim(),
          imap_port: imapPort,
          imap_username: form.imap_username.trim(),
          imap_password: form.imap_password,
          smtp_host: form.smtp_host.trim(),
          smtp_port: smtpPort,
          smtp_username: form.smtp_username.trim() || null,
          smtp_password: form.smtp_password,
        });
        toast.success("Conexão atualizada");
        onAccountsChanged?.(updated);
        onOpenChange(false);
      } catch (err) {
        setError(
          err instanceof ApiError
            ? err.message
            : err instanceof Error
              ? err.message
              : "Falha ao atualizar conexão."
        );
      } finally {
        setSaving(false);
      }
      return;
    }

    // mode === "create" — comportamento pré-existente.
    if (!form.display_name.trim()) {
      setError("Nome de exibição é obrigatório.");
      return;
    }
    if (!form.imap_host.trim() || !form.imap_username.trim() || !form.imap_password) {
      setError("Host, usuário e senha IMAP são obrigatórios.");
      return;
    }
    const imapPort = Number(form.imap_port);
    if (!Number.isFinite(imapPort) || imapPort <= 0 || imapPort > 65535) {
      setError("Porta IMAP inválida.");
      return;
    }
    if (!form.smtp_host.trim()) {
      setError("Host SMTP é obrigatório.");
      return;
    }
    const smtpPort = Number(form.smtp_port);
    if (!Number.isFinite(smtpPort) || smtpPort <= 0 || smtpPort > 65535) {
      setError("Porta SMTP inválida.");
      return;
    }

    if (!onSubmit) {
      setError("Handler de submit ausente.");
      return;
    }

    const payload: EmailAccountConnectPayload = {
      display_name: form.display_name.trim(),
      imap_host: form.imap_host.trim(),
      imap_port: imapPort,
      imap_username: form.imap_username.trim(),
      imap_password: form.imap_password,
      smtp_host: form.smtp_host.trim(),
      smtp_port: smtpPort,
      smtp_username: form.smtp_username.trim() || null,
      smtp_password: form.smtp_password || null,
    };

    setSaving(true);
    try {
      await onSubmit(payload);
      onOpenChange(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao conectar conta.");
    } finally {
      setSaving(false);
    }
  };

  const isEdit = mode === "edit";
  const submitLabel = saving
    ? isEdit
      ? "Salvando..."
      : "Conectando..."
    : isEdit
      ? "Salvar"
      : "Conectar";
  const helperTextId = "email-password-helper";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>
            {isEdit ? "Editar conexão de e-mail" : "Conectar conta de e-mail"}
          </DialogTitle>
          <DialogDescription>
            {isEdit
              ? "Atualize host/porta/usuário/senha IMAP e SMTP. Deixe as senhas em branco para manter a senha atual."
              : "Informe os dados do servidor IMAP (recebimento) e SMTP (envio). As credenciais são criptografadas por campo e nunca são devolvidas pela API. Provedores como Gmail e Yahoo exigem \"senha de app\" em vez da senha da conta."}
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 py-2">
          <div className="grid gap-2">
            <Label htmlFor="email-display-name">Nome de exibição *</Label>
            <Input
              id="email-display-name"
              placeholder="Conta pessoal"
              value={form.display_name}
              onChange={(e) =>
                setForm((f) => ({ ...f, display_name: e.target.value }))
              }
            />
          </div>

          <fieldset className="grid gap-2 rounded-md border border-border p-3">
            <legend className="px-1 text-xs font-medium text-muted-foreground">
              IMAP (recebimento)
            </legend>
            <div className="grid gap-3 sm:grid-cols-3">
              <div className="grid gap-1 sm:col-span-2">
                <Label htmlFor="email-imap-host">Host *</Label>
                <Input
                  id="email-imap-host"
                  placeholder="imap.example.com"
                  value={form.imap_host}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, imap_host: e.target.value }))
                  }
                />
              </div>
              <div className="grid gap-1">
                <Label htmlFor="email-imap-port">Porta *</Label>
                <Input
                  id="email-imap-port"
                  inputMode="numeric"
                  value={form.imap_port}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, imap_port: e.target.value }))
                  }
                />
              </div>
            </div>
            <div className="grid gap-1">
              <Label htmlFor="email-imap-username">Usuário *</Label>
              <Input
                id="email-imap-username"
                autoComplete="off"
                value={form.imap_username}
                onChange={(e) =>
                  setForm((f) => ({ ...f, imap_username: e.target.value }))
                }
              />
            </div>
            <div className="grid gap-1">
              <Label htmlFor="email-imap-password">
                Senha{isEdit ? "" : " *"}
              </Label>
              <Input
                id="email-imap-password"
                type="password"
                autoComplete="new-password"
                value={form.imap_password}
                aria-describedby={isEdit ? helperTextId : undefined}
                onChange={(e) =>
                  setForm((f) => ({ ...f, imap_password: e.target.value }))
                }
              />
            </div>
          </fieldset>

          <fieldset className="grid gap-2 rounded-md border border-border p-3">
            <legend className="px-1 text-xs font-medium text-muted-foreground">
              SMTP (envio)
            </legend>
            <div className="grid gap-3 sm:grid-cols-3">
              <div className="grid gap-1 sm:col-span-2">
                <Label htmlFor="email-smtp-host">Host *</Label>
                <Input
                  id="email-smtp-host"
                  placeholder="smtp.example.com"
                  value={form.smtp_host}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, smtp_host: e.target.value }))
                  }
                />
              </div>
              <div className="grid gap-1">
                <Label htmlFor="email-smtp-port">Porta *</Label>
                <Input
                  id="email-smtp-port"
                  inputMode="numeric"
                  value={form.smtp_port}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, smtp_port: e.target.value }))
                  }
                />
              </div>
            </div>
            <div className="grid gap-1">
              <Label htmlFor="email-smtp-username">
                Usuário (opcional)
              </Label>
              <Input
                id="email-smtp-username"
                autoComplete="off"
                value={form.smtp_username}
                onChange={(e) =>
                  setForm((f) => ({ ...f, smtp_username: e.target.value }))
                }
              />
            </div>
            <div className="grid gap-1">
              <Label htmlFor="email-smtp-password">
                Senha (opcional)
              </Label>
              <Input
                id="email-smtp-password"
                type="password"
                autoComplete="new-password"
                value={form.smtp_password}
                aria-describedby={isEdit ? helperTextId : undefined}
                onChange={(e) =>
                  setForm((f) => ({ ...f, smtp_password: e.target.value }))
                }
              />
            </div>
          </fieldset>

          {isEdit && (
            <p
              id={helperTextId}
              data-testid="email-password-helper"
              className="text-xs text-muted-foreground"
            >
              Deixe em branco para manter a senha atual.
            </p>
          )}

          {error && (
            <p className="text-sm text-destructive" role="alert">
              {error}
            </p>
          )}
        </div>
        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={saving}
          >
            Cancelar
          </Button>
          <Button type="button" onClick={handleSubmit} disabled={saving}>
            {submitLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
