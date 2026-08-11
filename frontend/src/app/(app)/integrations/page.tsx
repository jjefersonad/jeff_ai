"use client";

/**
 * "Integrações" screen (user-integrations-list-delete).
 *
 * Lists the authenticated user's `UserIntegration`s (mirroring the
 * `/mcp-servers` list layout) with a delete action per row. The header's
 * "Adicionar integração" button opens `AddIntegrationDialog` (type picker +
 * WhatsApp/Telegram generate-code flow); closing it re-runs `loadIntegrations()`.
 * The two always-visible WhatsApp/Telegram sections this page used to have
 * (`telegram-integration-frontend-registration`) were superseded by that
 * modal per explicit user correction; see `user-integrations-list-delete-design`.
 */

import { useCallback, useEffect, useState } from "react";
import { Plug, Plus } from "lucide-react";
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
import { Skeleton } from "@/components/ui/skeleton";
import { AddIntegrationDialog } from "@/components/integrations/add-integration-dialog";
import { ApiError } from "@/lib/api";
import {
  deleteUserIntegration,
  getIntegrationTypeMeta,
  listUserIntegrations,
  type UserIntegrationSummary,
} from "@/lib/integrations";

export default function IntegrationsPage() {
  const [integrations, setIntegrations] = useState<UserIntegrationSummary[] | null>(
    null
  );
  const [integrationsLoading, setIntegrationsLoading] = useState(true);
  const [integrationsError, setIntegrationsError] = useState<string | null>(null);

  const loadIntegrations = useCallback(async () => {
    setIntegrationsLoading(true);
    setIntegrationsError(null);
    try {
      const result = await listUserIntegrations();
      setIntegrations(result);
    } catch (err) {
      setIntegrationsError(
        err instanceof ApiError ? err.message : "Falha ao carregar integrações"
      );
    } finally {
      setIntegrationsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadIntegrations();
  }, [loadIntegrations]);

  const [deleteTarget, setDeleteTarget] = useState<UserIntegrationSummary | null>(null);
  const [deleting, setDeleting] = useState(false);

  const handleAskDelete = useCallback((integration: UserIntegrationSummary) => {
    setDeleteTarget(integration);
  }, []);

  const handleCancelDelete = useCallback(() => {
    setDeleteTarget(null);
  }, []);

  const handleConfirmDelete = useCallback(async () => {
    if (!deleteTarget || deleting) return;
    setDeleting(true);
    try {
      await deleteUserIntegration(deleteTarget.id);
      setIntegrations((prev) =>
        prev ? prev.filter((i) => i.id !== deleteTarget.id) : prev
      );
      toast.success("Integração excluída");
    } catch (err) {
      toast.error(
        err instanceof ApiError ? err.message : "Falha ao excluir integração"
      );
    } finally {
      setDeleting(false);
      setDeleteTarget(null);
    }
  }, [deleteTarget, deleting]);

  const [addDialogOpen, setAddDialogOpen] = useState(false);

  return (
    <div className="min-h-screen bg-background">
      <header className="sticky top-0 z-40 border-b border-border bg-background/80 backdrop-blur-sm">
        <div className="mx-auto flex max-w-[1000px] items-center gap-3 px-6 py-4">
          <Plug size={24} className="text-primary" aria-hidden="true" />
          <h1 className="text-xl font-semibold">Integrações</h1>
          <Button size="sm" className="ml-auto" onClick={() => setAddDialogOpen(true)}>
            <Plus className="mr-2 h-4 w-4" />
            Adicionar integração
          </Button>
        </div>
      </header>

      <main className="mx-auto max-w-[1000px] px-6 py-6">
        {integrationsError && (
          <p className="mb-4 text-sm text-destructive" role="alert">
            {integrationsError}
          </p>
        )}

        {integrationsLoading && !integrations && (
          <div className="space-y-3">
            <Skeleton className="h-14 w-full" />
            <Skeleton className="h-14 w-full" />
          </div>
        )}

        {!integrationsLoading && !integrationsError && integrations?.length === 0 && (
          <div className="rounded-md border border-dashed border-border py-16 text-center text-muted-foreground">
            <p>Você ainda não tem integrações configuradas</p>
          </div>
        )}

        {integrations && integrations.length > 0 && (
          <>
            {/* Desktop table */}
            <div className="hidden overflow-x-auto rounded-md border border-border md:block">
              <table className="w-full text-sm">
                <thead className="border-b border-border bg-muted/40 text-left">
                  <tr>
                    <th className="px-3 py-2 font-medium">Tipo</th>
                    <th className="px-3 py-2 font-medium">Criado em</th>
                    <th className="px-3 py-2 font-medium">Atualizado em</th>
                    <th className="px-3 py-2 font-medium">Ações</th>
                  </tr>
                </thead>
                <tbody>
                  {integrations.map((integration) => {
                    const meta = getIntegrationTypeMeta(integration.integration_type);
                    const Icon = meta.icon;
                    return (
                      <tr
                        key={integration.id}
                        className="border-b border-border last:border-0"
                      >
                        <td className="px-3 py-2">
                          <div className="flex items-center gap-2">
                            <Icon className="h-4 w-4 text-muted-foreground" />
                            <span>{meta.label}</span>
                          </div>
                        </td>
                        <td className="px-3 py-2 text-muted-foreground">
                          {new Date(integration.created_at).toLocaleString()}
                        </td>
                        <td className="px-3 py-2 text-muted-foreground">
                          {new Date(integration.updated_at).toLocaleString()}
                        </td>
                        <td className="px-3 py-2">
                          <Button
                            variant="ghost"
                            size="sm"
                            aria-label={`Excluir ${meta.label}`}
                            onClick={() => handleAskDelete(integration)}
                          >
                            Excluir
                          </Button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* Mobile cards */}
            <ul className="flex flex-col gap-3 md:hidden">
              {integrations.map((integration) => {
                const meta = getIntegrationTypeMeta(integration.integration_type);
                const Icon = meta.icon;
                return (
                  <li
                    key={integration.id}
                    className="rounded-md border border-border p-3"
                  >
                    <div className="flex items-center gap-2">
                      <Icon className="h-4 w-4 text-muted-foreground" />
                      <span className="font-medium">{meta.label}</span>
                    </div>
                    <p className="mt-1 text-xs text-muted-foreground">
                      Atualizado {new Date(integration.updated_at).toLocaleString()}
                    </p>
                    <div className="mt-2">
                      <Button
                        variant="outline"
                        size="sm"
                        aria-label={`Excluir ${meta.label}`}
                        onClick={() => handleAskDelete(integration)}
                      >
                        Excluir
                      </Button>
                    </div>
                  </li>
                );
              })}
            </ul>
          </>
        )}
      </main>

      <Dialog
        open={deleteTarget != null}
        onOpenChange={(open) => {
          if (!open) handleCancelDelete();
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Excluir integração?</DialogTitle>
            <DialogDescription>
              Isso remove a integração{" "}
              {deleteTarget && getIntegrationTypeMeta(deleteTarget.integration_type).label}.
              Esta ação não pode ser desfeita.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={handleCancelDelete}>
              Cancelar
            </Button>
            <Button
              type="button"
              variant="destructive"
              onClick={handleConfirmDelete}
              disabled={deleting}
            >
              Excluir
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <AddIntegrationDialog
        open={addDialogOpen}
        onOpenChange={setAddDialogOpen}
        onLinked={loadIntegrations}
      />
    </div>
  );
}
