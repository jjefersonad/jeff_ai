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
import type {
  McpServerSummary,
  ServerWritePayload,
} from "@/app/lib/mcp";
import { KeyValueRows } from "./KeyValueRows";

interface McpServerDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** undefined = creating a new server; defined = editing this one. */
  editing?: McpServerSummary;
  /**
   * Receives the form payload (with the form-supplied `name`). The
   * transport is determined by the dialog's transport selector and the
   * variant is narrowed accordingly; see `ServerWritePayload`.
   */
  onSubmit: (payload: { name: string } & ServerWritePayload) => Promise<void>;
}

/**
 * Transport-aware editor for MCP servers (REQ-004 of
 * `user-scoped-mcp-config-storage`, proposal Impact).
 *
 * Two `mcp_admin_api.py`-matching variants on a discriminated union:
 * - `stdio` (process local)
 * - `http`  (URL remota — Zernio usa este)
 *
 * Variantes `stdio` exigem `command` + (opcionalmente) `args` e `env`;
 * variantes `http` exigem `url` + (opcionalmente) `headers`. As
 * variáveis sensíveis (resolvidas em runtime a partir do `backend/.env`)
 * nunca cruzam o navegador — o usuário digita aqui só o NOME da env var
 * (REQ-007), nunca o valor.
 *
 * Os pares chave→envVar ficam dentro de `KeyValueRows`, que dispara
 * `onChange` em cada adição/remoção/edição; o estado pai (`envMap`/
 * `headersMap`) é então montado no `ServerWritePayload` no submit.
 */
export function McpServerDialog({
  open,
  onOpenChange,
  editing,
  onSubmit,
}: McpServerDialogProps) {
  const [name, setName] = useState("");
  const [transport, setTransport] =
    useState<ServerWritePayload["transport"]>("stdio");
  const [command, setCommand] = useState("");
  const [argsText, setArgsText] = useState("");
  const [url, setUrl] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // env / headers ficam dentro do `KeyValueRows`; capturamos o último
  // valor emitido por `onChange` para usar no submit.
  const [envMap, setEnvMap] = useState<Record<string, string>>({});
  const [headersMap, setHeadersMap] = useState<Record<string, string>>({});

  useEffect(() => {
    if (!open) return;
    setName(editing?.name ?? "");
    setTransport("stdio");
    setCommand(editing?.command ?? "");
    setArgsText((editing?.args ?? []).join(" "));
    setEnvMap(editing?.env ?? {});
    setUrl("");
    setHeadersMap({});
    setError(null);
  }, [open, editing]);

  const handleSubmit = async () => {
    if (!name.trim()) {
      setError("Nome é obrigatório.");
      return;
    }
    if (transport === "stdio" && !command.trim()) {
      setError("Comando é obrigatório para o transporte stdio.");
      return;
    }
    if (transport === "http" && !url.trim()) {
      setError("URL é obrigatória para o transporte http.");
      return;
    }

    let payload: { name: string } & ServerWritePayload;
    if (transport === "stdio") {
      payload = {
        name: name.trim(),
        transport: "stdio",
        command: command.trim(),
        args: argsText.trim() ? argsText.trim().split(/\s+/) : [],
        env: envMap,
      };
    } else {
      payload = {
        name: name.trim(),
        transport: "http",
        url: url.trim(),
        headers: headersMap,
      };
    }

    setSaving(true);
    setError(null);
    try {
      await onSubmit(payload);
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
          <DialogTitle>
            {editing ? "Editar servidor MCP" : "Adicionar servidor MCP"}
          </DialogTitle>
          <DialogDescription>
            Credenciais nunca são digitadas aqui — informe o NOME da variável
            de ambiente definida em <code>backend/.env</code>; o valor nunca
            passa pelo navegador (REQ-007). Suporte a transporte{" "}
            <code>stdio</code> (processo local) e <code>http</code> (endpoint
            remoto) — preencha só os campos do transporte escolhido
            (Zernio, por exemplo, é <code>http</code>).
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
            <Label htmlFor="mcp-transport">Transporte</Label>
            <select
              id="mcp-transport"
              value={transport}
              onChange={(e) =>
                setTransport(e.target.value as ServerWritePayload["transport"])
              }
              className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
            >
              <option value="stdio">stdio (processo local)</option>
              <option value="http">http (endpoint remoto)</option>
            </select>
          </div>

          {transport === "stdio" && (
            <>
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
                <Label htmlFor="mcp-args">
                  Argumentos (separados por espaço)
                </Label>
                <Input
                  id="mcp-args"
                  placeholder="-y @modelcontextprotocol/server-example"
                  value={argsText}
                  onChange={(e) => setArgsText(e.target.value)}
                />
              </div>
              <KeyValueRows
                key={`env-${editing?.name ?? "new"}-${open}`}
                label="Variáveis de ambiente (referência, não valor)"
                emptyHint="Nenhuma. Adicione se o servidor exigir uma credencial."
                keyPlaceholder="chave (ex: API_KEY)"
                valuePlaceholder="nome da env var (ex: MEU_SERVIDOR_API_KEY)"
                initial={envMap}
                onChange={setEnvMap}
              />
            </>
          )}

          {transport === "http" && (
            <>
              <div className="grid gap-2">
                <Label htmlFor="mcp-url">URL do endpoint</Label>
                <Input
                  id="mcp-url"
                  placeholder="https://mcp.exemplo.com/mcp"
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                />
              </div>
              <KeyValueRows
                key={`headers-${editing?.name ?? "new"}-${open}`}
                label="Headers (referência, não valor)"
                emptyHint="Nenhum. Adicione se o endpoint exigir autenticação — exemplo: Authorization → ${ZERNIO_TOKEN}."
                keyPlaceholder="nome do header (ex: Authorization)"
                valuePlaceholder="nome da env var (ex: ZERNIO_TOKEN)"
                initial={headersMap}
                onChange={setHeadersMap}
              />
            </>
          )}

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
