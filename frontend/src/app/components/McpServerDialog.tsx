"use client";

import { useEffect, useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Plus, Trash2 } from "lucide-react";
import type { McpServerSummary } from "@/app/lib/mcp";

interface EnvVarRow {
  key: string;
  varName: string;
}

interface McpServerDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** undefined = creating a new server; defined = editing this one. */
  editing?: McpServerSummary;
  onSubmit: (payload: {
    name: string;
    command: string;
    args: string[];
    env: Record<string, string>;
  }) => Promise<void>;
}

export function McpServerDialog({
  open,
  onOpenChange,
  editing,
  onSubmit,
}: McpServerDialogProps) {
  const [name, setName] = useState("");
  const [command, setCommand] = useState("");
  const [argsText, setArgsText] = useState("");
  const [envRows, setEnvRows] = useState<EnvVarRow[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setName(editing?.name ?? "");
    setCommand(editing?.command ?? "");
    setArgsText((editing?.args ?? []).join(" "));
    setEnvRows(
      Object.entries(editing?.env ?? {}).map(([key, varName]) => ({
        key,
        varName,
      }))
    );
    setError(null);
  }, [open, editing]);

  const addEnvRow = () => setEnvRows((rows) => [...rows, { key: "", varName: "" }]);
  const removeEnvRow = (index: number) =>
    setEnvRows((rows) => rows.filter((_, i) => i !== index));
  const updateEnvRow = (index: number, field: keyof EnvVarRow, value: string) =>
    setEnvRows((rows) =>
      rows.map((row, i) => (i === index ? { ...row, [field]: value } : row))
    );

  const handleSubmit = async () => {
    if (!name.trim() || !command.trim()) {
      setError("Nome e comando são obrigatórios.");
      return;
    }
    const env: Record<string, string> = {};
    for (const row of envRows) {
      if (!row.key.trim()) continue;
      env[row.key.trim()] = row.varName.trim();
    }
    setSaving(true);
    setError(null);
    try {
      await onSubmit({
        name: name.trim(),
        command: command.trim(),
        args: argsText.trim() ? argsText.trim().split(/\s+/) : [],
        env,
      });
      onOpenChange(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao salvar servidor.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[560px]">
        <DialogHeader>
          <DialogTitle>{editing ? "Editar servidor MCP" : "Adicionar servidor MCP"}</DialogTitle>
          <DialogDescription>
            Só transporte <code>stdio</code> é suportado. Credenciais nunca são
            digitadas aqui — informe o NOME da variável de ambiente definida em{" "}
            <code>backend/.env</code>; o valor nunca passa pelo navegador.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 py-2">
          <div className="grid gap-2">
            <Label htmlFor="mcp-name">Nome</Label>
            <Input
              id="mcp-name"
              placeholder="meu-servidor"
              value={name}
              onChange={(e) => setName(e.target.value)}
              disabled={!!editing}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="mcp-command">Comando</Label>
            <Input
              id="mcp-command"
              placeholder="npx"
              value={command}
              onChange={(e) => setCommand(e.target.value)}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="mcp-args">Argumentos (separados por espaço)</Label>
            <Input
              id="mcp-args"
              placeholder="-y @modelcontextprotocol/server-example"
              value={argsText}
              onChange={(e) => setArgsText(e.target.value)}
            />
          </div>
          <div className="grid gap-2">
            <div className="flex items-center justify-between">
              <Label>Variáveis de ambiente (referência, não valor)</Label>
              <button
                type="button"
                onClick={addEnvRow}
                className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
              >
                <Plus className="h-3 w-3" />
                Adicionar
              </button>
            </div>
            {envRows.length === 0 && (
              <p className="text-xs text-muted-foreground">
                Nenhuma. Adicione se o servidor exigir uma credencial.
              </p>
            )}
            {envRows.map((row, index) => (
              <div key={index} className="flex items-center gap-2">
                <Input
                  placeholder="chave (ex: API_KEY)"
                  value={row.key}
                  onChange={(e) => updateEnvRow(index, "key", e.target.value)}
                />
                <Input
                  placeholder="nome da env var (ex: MEU_SERVIDOR_API_KEY)"
                  value={row.varName}
                  onChange={(e) => updateEnvRow(index, "varName", e.target.value)}
                />
                <button
                  type="button"
                  onClick={() => removeEnvRow(index)}
                  className="shrink-0 text-muted-foreground hover:text-destructive"
                  aria-label="Remover"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            ))}
          </div>
          {error && <p className="text-sm text-destructive">{error}</p>}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancelar
          </Button>
          <Button onClick={handleSubmit} disabled={saving}>
            {saving ? "Salvando..." : "Salvar"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
