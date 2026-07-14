"use client";

import { useEffect, useState, useCallback } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import {
  fetchCapabilities,
  fetchServerTools,
  setToolCapability,
  clearToolCapability,
  type McpToolInfo,
} from "@/app/lib/mcp";

interface McpServerToolsDialogProps {
  serverName: string | null;
  onOpenChange: (open: boolean) => void;
}

/**
 * `unknown` is the safe fail-closed default (Tier 3+ gate) — a human must
 * explicitly relax it. See `effects.py` Q3 / task-mcp-3 acceptance criteria.
 */
function capabilityBadgeClass(capability: string): string {
  if (capability === "unknown") return "bg-muted text-muted-foreground";
  return "bg-primary/15 text-primary";
}

export function McpServerToolsDialog({
  serverName,
  onOpenChange,
}: McpServerToolsDialogProps) {
  const [tools, setTools] = useState<McpToolInfo[]>([]);
  const [capabilities, setCapabilities] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [updating, setUpdating] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!serverName) return;
    setLoading(true);
    setError(null);
    try {
      const [toolsResult, capsResult] = await Promise.all([
        fetchServerTools(serverName),
        capabilities.length ? Promise.resolve(capabilities) : fetchCapabilities(),
      ]);
      setTools(toolsResult);
      setCapabilities(capsResult);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao listar tools.");
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [serverName]);

  useEffect(() => {
    if (serverName) load();
  }, [serverName, load]);

  const handleCapabilityChange = async (tool: McpToolInfo, next: string) => {
    setUpdating(tool.qualified_name);
    try {
      if (next === "unknown") {
        await clearToolCapability(tool.qualified_name);
      } else {
        await setToolCapability(tool.qualified_name, next);
      }
      setTools((prev) =>
        prev.map((t) =>
          t.qualified_name === tool.qualified_name ? { ...t, capability: next } : t
        )
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao classificar tool.");
    } finally {
      setUpdating(null);
    }
  };

  return (
    <Dialog open={!!serverName} onOpenChange={(open) => !open && onOpenChange(false)}>
      <DialogContent className="sm:max-w-[680px] max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Tools de {serverName}</DialogTitle>
          <DialogDescription>
            Classificar uma tool é um ato humano — nenhuma heurística do
            agente pode rebaixar a capacidade dela. O default seguro é{" "}
            <code>unknown</code> (exige aprovação humana a cada uso).
          </DialogDescription>
        </DialogHeader>

        {loading && (
          <div className="space-y-2">
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
          </div>
        )}

        {error && <p className="text-sm text-destructive">{error}</p>}

        {!loading && !error && tools.length === 0 && (
          <p className="text-sm text-muted-foreground">
            Este servidor não expõe nenhuma tool.
          </p>
        )}

        {!loading && tools.length > 0 && (
          <div className="space-y-3">
            {tools.map((tool) => (
              <div
                key={tool.qualified_name}
                className="flex items-start justify-between gap-4 rounded-md border border-border p-3"
              >
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-sm font-medium">{tool.name}</span>
                    <span
                      className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${capabilityBadgeClass(
                        tool.capability
                      )}`}
                    >
                      {tool.capability}
                    </span>
                  </div>
                  <p className="mt-1 truncate text-xs text-muted-foreground">
                    {tool.description || "(sem descrição)"}
                  </p>
                  <p className="mt-0.5 font-mono text-[10px] text-muted-foreground">
                    {tool.qualified_name}
                  </p>
                </div>
                <Select
                  value={tool.capability}
                  onValueChange={(v) => handleCapabilityChange(tool, v)}
                  disabled={updating === tool.qualified_name}
                >
                  <SelectTrigger className="w-[140px] shrink-0">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {capabilities.map((cap) => (
                      <SelectItem key={cap} value={cap}>
                        {cap}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            ))}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
