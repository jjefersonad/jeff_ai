"use client";

import { useCallback, useState } from "react";
import useSWR from "swr";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Plug, Plus, Pencil, Trash2, Wrench } from "lucide-react";
import { McpServerDialog } from "@/app/components/McpServerDialog";
import { McpServerToolsDialog } from "@/app/components/McpServerToolsDialog";
import {
  fetchServers,
  createServer,
  updateServer,
  deleteServer,
  type McpServerSummary,
} from "@/app/lib/mcp";

const STATUS_STYLES: Record<McpServerSummary["status"], string> = {
  connected: "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400",
  offline: "bg-amber-500/15 text-amber-600 dark:text-amber-400",
  error: "bg-destructive/15 text-destructive",
};

const STATUS_LABELS: Record<McpServerSummary["status"], string> = {
  connected: "Conectado",
  offline: "Offline",
  error: "Erro",
};

export default function McpServersPage() {
  const { data, error, isLoading, mutate } = useSWR<McpServerSummary[]>(
    "mcp-servers",
    fetchServers,
    { refreshInterval: 15_000 }
  );

  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<McpServerSummary | undefined>(undefined);
  const [toolsFor, setToolsFor] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);

  const openCreate = useCallback(() => {
    setEditing(undefined);
    setDialogOpen(true);
  }, []);

  const openEdit = useCallback((server: McpServerSummary) => {
    setEditing(server);
    setDialogOpen(true);
  }, []);

  const handleSubmit = useCallback(
    async (payload: {
      name: string;
      command: string;
      args: string[];
      env: Record<string, string>;
    }) => {
      if (editing) {
        await updateServer(editing.name, payload);
      } else {
        await createServer(payload.name, payload);
      }
      await mutate();
    },
    [editing, mutate]
  );

  const handleDelete = useCallback(
    async (name: string) => {
      if (!confirm(`Remover o servidor MCP "${name}"? Esta ação não pode ser desfeita.`)) {
        return;
      }
      setDeleting(name);
      try {
        await deleteServer(name);
        await mutate();
      } finally {
        setDeleting(null);
      }
    },
    [mutate]
  );

  return (
    <div className="min-h-screen bg-background">
      <header className="sticky top-0 z-40 border-b border-border bg-background/80 backdrop-blur-sm">
        <div className="mx-auto flex max-w-[1000px] items-center gap-3 px-6 py-4">
          <Plug size={24} className="text-primary" />
          <h1 className="text-xl font-semibold">Servidores MCP</h1>
          <span className="ml-2 text-sm text-muted-foreground">
            Capacidade nº 4 — plugue ferramentas de terceiros no agente
          </span>
          <Button size="sm" className="ml-auto" onClick={openCreate}>
            <Plus className="mr-2 h-4 w-4" />
            Adicionar servidor
          </Button>
        </div>
      </header>

      <main className="mx-auto max-w-[1000px] px-6 py-6">
        {error && (
          <div className="flex flex-col items-center justify-center py-16 text-destructive">
            <p className="text-lg font-medium">Erro ao carregar servidores</p>
            <p className="mt-1 text-sm">{error.message}</p>
          </div>
        )}

        {isLoading && !data && (
          <div className="space-y-3">
            <Skeleton className="h-20 w-full" />
            <Skeleton className="h-20 w-full" />
          </div>
        )}

        {!isLoading && !error && data?.length === 0 && (
          <div className="rounded-md border border-dashed border-border py-16 text-center text-muted-foreground">
            <p>Nenhum servidor MCP configurado ainda.</p>
            <p className="mt-1 text-sm">
              O agente não pode adicionar um por conta própria — isso é sempre
              um ato humano.
            </p>
          </div>
        )}

        <div className="space-y-3">
          {data?.map((server) => (
            <div
              key={server.name}
              className="rounded-md border border-border bg-card p-4"
            >
              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <h2 className="font-mono text-sm font-semibold">{server.name}</h2>
                    <span
                      className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${STATUS_STYLES[server.status]}`}
                    >
                      {STATUS_LABELS[server.status]}
                    </span>
                    {server.status === "connected" && (
                      <span className="text-xs text-muted-foreground">
                        {server.tool_count} tool{server.tool_count === 1 ? "" : "s"}
                      </span>
                    )}
                  </div>
                  <p className="mt-1 truncate font-mono text-xs text-muted-foreground">
                    {server.command} {server.args.join(" ")}
                  </p>
                  {server.message && (
                    <p className="mt-1 text-xs text-destructive">{server.message}</p>
                  )}
                  {Object.keys(server.env).length > 0 && (
                    <p className="mt-1 text-xs text-muted-foreground">
                      env:{" "}
                      {Object.entries(server.env)
                        .map(([k, v]) => `${k}=\${${v}}`)
                        .join(", ")}
                    </p>
                  )}
                </div>
                <div className="flex shrink-0 items-center gap-1">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setToolsFor(server.name)}
                    disabled={server.status !== "connected"}
                  >
                    <Wrench className="mr-1 h-3.5 w-3.5" />
                    Tools
                  </Button>
                  <Button variant="ghost" size="sm" onClick={() => openEdit(server)}>
                    <Pencil className="h-3.5 w-3.5" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => handleDelete(server.name)}
                    disabled={deleting === server.name}
                    className="text-destructive hover:text-destructive"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </div>
              </div>
            </div>
          ))}
        </div>
      </main>

      <McpServerDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        editing={editing}
        onSubmit={handleSubmit}
      />
      <McpServerToolsDialog serverName={toolsFor} onOpenChange={() => setToolsFor(null)} />
    </div>
  );
}
