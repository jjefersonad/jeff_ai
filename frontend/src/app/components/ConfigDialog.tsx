"use client";

import { useState, useEffect, useCallback } from "react";
import { Client, Assistant } from "@langchain/langgraph-sdk";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
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
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { StandaloneConfig } from "@/lib/config";
import { RefreshCw } from "lucide-react";

interface ConfigDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSave: (config: StandaloneConfig) => void;
  initialConfig?: StandaloneConfig;
}

interface GraphOption {
  graphId: string;
  name: string;
}

export function ConfigDialog({
  open,
  onOpenChange,
  onSave,
  initialConfig,
}: ConfigDialogProps) {
  const [deploymentUrl, setDeploymentUrl] = useState(
    initialConfig?.deploymentUrl || ""
  );
  const [assistantId, setAssistantId] = useState(
    initialConfig?.assistantId || ""
  );
  const [langsmithApiKey, setLangsmithApiKey] = useState(
    initialConfig?.langsmithApiKey || ""
  );

  const [assistants, setAssistants] = useState<GraphOption[]>([]);
  const [loadingAssistants, setLoadingAssistants] = useState(false);
  const [assistantsError, setAssistantsError] = useState<string | null>(null);
  // Permite digitar o Assistant ID manualmente caso a busca falhe/venha vazia.
  const [manualEntry, setManualEntry] = useState(false);

  useEffect(() => {
    if (open && initialConfig) {
      setDeploymentUrl(initialConfig.deploymentUrl);
      setAssistantId(initialConfig.assistantId);
      setLangsmithApiKey(initialConfig.langsmithApiKey || "");
      setManualEntry(false);
    }
  }, [open, initialConfig]);

  const fetchAssistants = useCallback(async () => {
    if (!deploymentUrl) {
      setAssistants([]);
      return;
    }

    setLoadingAssistants(true);
    setAssistantsError(null);

    try {
      const client = new Client({
        apiUrl: deploymentUrl,
        defaultHeaders: {
          "Content-Type": "application/json",
          "X-Api-Key": langsmithApiKey,
        },
      });

      const results = await client.assistants.search({ limit: 100 });

      // Deduplica por graph_id (pode haver múltiplos assistants por grafo).
      const byGraph = new Map<string, GraphOption>();
      for (const a of results as Assistant[]) {
        if (!a.graph_id) continue;
        if (!byGraph.has(a.graph_id)) {
          byGraph.set(a.graph_id, {
            graphId: a.graph_id,
            name: a.name && a.name !== a.graph_id ? a.name : a.graph_id,
          });
        }
      }

      const options = Array.from(byGraph.values()).sort((x, y) =>
        x.graphId.localeCompare(y.graphId)
      );
      setAssistants(options);

      if (options.length === 0) {
        setManualEntry(true);
      } else if (
        assistantId &&
        !options.some((o) => o.graphId === assistantId)
      ) {
        // O ID salvo não existe mais na lista — deixa visível via entrada manual.
        setManualEntry(true);
      }
    } catch (error) {
      console.error("Failed to fetch assistants:", error);
      setAssistantsError(
        error instanceof Error ? error.message : "Failed to fetch assistants"
      );
      setManualEntry(true);
    } finally {
      setLoadingAssistants(false);
    }
  }, [deploymentUrl, langsmithApiKey, assistantId]);

  // Busca a lista quando o modal abre e quando a URL/API key mudam (com debounce).
  useEffect(() => {
    if (!open) return;
    const timer = setTimeout(() => {
      fetchAssistants();
    }, 400);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, deploymentUrl, langsmithApiKey]);

  const handleSave = () => {
    if (!deploymentUrl || !assistantId) {
      alert("Please fill in all required fields");
      return;
    }

    onSave({
      deploymentUrl,
      assistantId,
      langsmithApiKey: langsmithApiKey || undefined,
    });
    onOpenChange(false);
  };

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
    >
      <DialogContent className="sm:max-w-[525px]">
        <DialogHeader>
          <DialogTitle>Configuration</DialogTitle>
          <DialogDescription>
            Configure your LangGraph deployment settings. These settings are
            saved in your browser&apos;s local storage.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 py-4">
          <div className="grid gap-2">
            <Label htmlFor="deploymentUrl">Deployment URL</Label>
            <Input
              id="deploymentUrl"
              placeholder="https://<deployment-url>"
              value={deploymentUrl}
              onChange={(e) => setDeploymentUrl(e.target.value)}
            />
          </div>
          <div className="grid gap-2">
            <div className="flex items-center justify-between">
              <Label htmlFor="assistantId">Assistant</Label>
              <button
                type="button"
                onClick={() => fetchAssistants()}
                disabled={!deploymentUrl || loadingAssistants}
                className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground disabled:opacity-50"
              >
                <RefreshCw
                  className={`h-3 w-3 ${loadingAssistants ? "animate-spin" : ""}`}
                />
                Reload
              </button>
            </div>

            {manualEntry ? (
              <Input
                id="assistantId"
                placeholder="<assistant-id or graph-id>"
                value={assistantId}
                onChange={(e) => setAssistantId(e.target.value)}
              />
            ) : (
              <Select
                value={assistantId}
                onValueChange={setAssistantId}
                disabled={loadingAssistants || assistants.length === 0}
              >
                <SelectTrigger id="assistantId">
                  <SelectValue
                    placeholder={
                      loadingAssistants
                        ? "Loading assistants..."
                        : !deploymentUrl
                          ? "Enter a deployment URL first"
                          : "Select an assistant"
                    }
                  />
                </SelectTrigger>
                <SelectContent>
                  {assistants.map((a) => (
                    <SelectItem
                      key={a.graphId}
                      value={a.graphId}
                    >
                      {a.name}
                      {a.name !== a.graphId ? ` (${a.graphId})` : ""}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}

            {assistantsError && (
              <p className="text-xs text-destructive">
                {assistantsError} — you can type the ID manually.
              </p>
            )}
            <button
              type="button"
              onClick={() => setManualEntry((v) => !v)}
              className="self-start text-xs text-muted-foreground underline hover:text-foreground"
            >
              {manualEntry ? "Choose from list" : "Enter ID manually"}
            </button>
          </div>
          <div className="grid gap-2">
            <Label htmlFor="langsmithApiKey">
              LangSmith API Key{" "}
              <span className="text-muted-foreground">(Optional)</span>
            </Label>
            <Input
              id="langsmithApiKey"
              type="password"
              placeholder="lsv2_pt_..."
              value={langsmithApiKey}
              onChange={(e) => setLangsmithApiKey(e.target.value)}
            />
          </div>
        </div>
        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
          >
            Cancel
          </Button>
          <Button onClick={handleSave}>Save</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
