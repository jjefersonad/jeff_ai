"use client";

import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { AlertCircle, Check, X, Pencil, GitCommit } from "lucide-react";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";
import type { ActionRequest, ReviewConfig } from "@/app/types/types";
import { cn } from "@/lib/utils";

interface ToolApprovalInterruptProps {
  actionRequest: ActionRequest;
  reviewConfig?: ReviewConfig;
  onResume: (value: any) => void;
  isLoading?: boolean;
}

/**
 * Marcador informal backend↔frontend que o backend (`tier_config.DIFF_MARKER`)
 * prefixa em toda `description` que contém um diff. Se a string começa com
 * isso, o componente renderiza `<DiffPreview>` em vez do JSON cru. É um
 * acordo local — não está no schema do langchain, é só um prefixo dentro
 * do campo `description` que já existe. Ver design D2 de
 * `unified-dev-agent-design` (REBASED 2026-07-13).
 */
const DIFF_MARKER = "<<<DIFF>>>";

/**
 * Tools Tier 3 com preview de mensagem de commit editável inline. O
 * frontend detecta pelo nome e abre um `<GitCommitMessageEditor>` em vez
 * do editor de args JSON genérico.
 */
const GIT_COMMIT_TOOL = "git_commit";

/**
 * Extrai a primeira string de path dos args. Usado para mostrar o
 * "Arquivo: X" no header do diff e na barra de tool info. Não
 * afeta renderização — só display.
 */
function pathFromArgs(args: Record<string, unknown>): string | undefined {
  const direct = args.path;
  if (typeof direct === "string") return direct;
  const edits = args.edits;
  if (Array.isArray(edits) && edits.length > 0) {
    const first = edits[0];
    if (typeof first === "object" && first !== null) {
      const p = (first as Record<string, unknown>).path;
      if (typeof p === "string") return p;
    }
  }
  return undefined;
}

/**
 * Quebra o body do diff em linhas tipadas. As linhas `+` / `-` / ` `
 * recebem classes CSS para colorização verde/vermelho/cinza. Linhas de
 * cabeçalho `@@ ... @@` ficam em itálico.
 */
type DiffLine =
  | { kind: "add"; text: string }
  | { kind: "del"; text: string }
  | { kind: "ctx"; text: string }
  | { kind: "hunk"; text: string }
  | { kind: "other"; text: string };

function parseDiffLines(body: string): DiffLine[] {
  const out: DiffLine[] = [];
  for (const raw of body.split("\n")) {
    if (raw.startsWith("@@")) {
      out.push({ kind: "hunk", text: raw });
    } else if (raw.startsWith("+")) {
      out.push({ kind: "add", text: raw.slice(1) });
    } else if (raw.startsWith("-")) {
      out.push({ kind: "del", text: raw.slice(1) });
    } else if (raw.startsWith(" ")) {
      out.push({ kind: "ctx", text: raw.slice(1) });
    } else {
      out.push({ kind: "other", text: raw });
    }
  }
  return out;
}

/**
 * Renderiza um diff prefixado por `<<<DIFF>>>`. Formato esperado:
 *
 *     <<<DIFF>>>header text
 *
 *     ```diff
 *     @@ -1,1 +1,1 @@
 *     -old
 *     +new
 *     ```
 *
 * O header é a primeira linha; o bloco ```diff``` é extraído por regex
 * (não usamos um parser markdown completo — não vale a dependência).
 */
function DiffPreview({ description }: { description: string }) {
  // Strip do marcador e separa header do body.
  const stripped = description.startsWith(DIFF_MARKER)
    ? description.slice(DIFF_MARKER.length)
    : description;

  const diffBlockMatch = stripped.match(/```diff\n([\s\S]*?)\n```/);
  const header = stripped
    .replace(/```diff\n[\s\S]*?\n```/, "")
    .trim();
  const body = diffBlockMatch ? diffBlockMatch[1] : stripped;

  const lines = useMemo(() => parseDiffLines(body), [body]);

  return (
    <div className="mt-2 overflow-hidden rounded-sm border border-border bg-background">
      {header && (
        <div className="border-b border-border bg-muted/40 px-3 py-1.5 font-mono text-xs text-muted-foreground">
          {header}
        </div>
      )}
      <div className="overflow-x-auto font-mono text-xs leading-relaxed">
        {lines.map((ln, i) => {
          const lineNo = i + 1;
          const lineNumberEl = (
            <span
              aria-hidden
              className="select-none pr-3 text-right text-muted-foreground/60"
              style={{ display: "inline-block", minWidth: "3ch" }}
            >
              {lineNo}
            </span>
          );
          if (ln.kind === "hunk") {
            return (
              <div
                key={i}
                className="px-3 italic text-muted-foreground"
                style={{ backgroundColor: "rgba(127,127,127,0.08)" }}
              >
                {lineNumberEl}
                <span>{ln.text}</span>
              </div>
            );
          }
          if (ln.kind === "add") {
            return (
              <div
                key={i}
                className="px-3 text-green-700 dark:text-green-400"
                style={{ backgroundColor: "rgba(46,160,67,0.12)" }}
              >
                {lineNumberEl}
                <span>+ </span>
                <span>{ln.text}</span>
              </div>
            );
          }
          if (ln.kind === "del") {
            return (
              <div
                key={i}
                className="px-3 text-red-700 dark:text-red-400"
                style={{ backgroundColor: "rgba(248,81,73,0.10)" }}
              >
                {lineNumberEl}
                <span>- </span>
                <span>{ln.text}</span>
              </div>
            );
          }
          if (ln.kind === "ctx") {
            return (
              <div key={i} className="px-3 text-muted-foreground">
                {lineNumberEl}
                <span>  </span>
                <span>{ln.text}</span>
              </div>
            );
          }
          // `other` (linhas `--- a/`, `+++ b/`, etc.)
          return (
            <div key={i} className="px-3 text-muted-foreground">
              {lineNumberEl}
              <span>{ln.text}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/**
 * Editor inline da mensagem de commit. Substitui o "Edit" genérico (que
 * abre o editor JSON) por um Textarea simples focado em `args.message`.
 * O usuário pode editar a mensagem e aprovar — o frontend envia a decisão
 * `edit` com `args.message` atualizado, idêntico ao protocolo dos outros
 * tools.
 */
function GitCommitMessageEditor({
  initialMessage,
  onConfirm,
  onCancel,
  isLoading,
}: {
  initialMessage: string;
  onConfirm: (newMessage: string) => void;
  onCancel: () => void;
  isLoading?: boolean;
}) {
  const [msg, setMsg] = useState(initialMessage);
  return (
    <div className="space-y-2">
      <label className="block text-xs font-medium text-foreground">
        Commit message
      </label>
      <Textarea
        value={msg}
        onChange={(e) => setMsg(e.target.value)}
        rows={3}
        className="font-mono text-xs"
        disabled={isLoading}
        placeholder="Mensagem do commit…"
      />
      <div className="flex gap-2">
        <Button
          variant="outline"
          size="sm"
          onClick={onCancel}
          disabled={isLoading}
        >
          Cancel
        </Button>
        <Button
          size="sm"
          onClick={() => onConfirm(msg)}
          disabled={isLoading || msg.trim().length === 0}
          className="bg-green-600 text-white hover:bg-green-700"
        >
          <Check size={14} />
          {isLoading ? "Saving..." : "Save Message & Approve"}
        </Button>
      </div>
    </div>
  );
}

export function ToolApprovalInterrupt({
  actionRequest,
  reviewConfig,
  onResume,
  isLoading,
}: ToolApprovalInterruptProps) {
  const [rejectionMessage, setRejectionMessage] = useState("");
  const [isEditing, setIsEditing] = useState(false);
  const [editedArgs, setEditedArgs] = useState<Record<string, unknown>>({});
  const [showRejectionInput, setShowRejectionInput] = useState(false);

  const allowedDecisions = reviewConfig?.allowedDecisions ?? [
    "approve",
    "reject",
    "edit",
  ];

  // Detect diff: o backend prefixa `<<<DIFF>>>` na `description` quando há
  // preview. Para tools sem diff, o componente mostra `args` como JSON (como
  // antes desta task).
  const hasDiff = useMemo(
    () =>
      typeof actionRequest.description === "string" &&
      actionRequest.description.startsWith(DIFF_MARKER),
    [actionRequest.description],
  );

  // `git_commit` tem fluxo de edição dedicado (mensagem inline). Outras
  // tools Tier 3 com diff caem no editor JSON genérico se o user quiser
  // ajustar algo.
  const isGitCommit = actionRequest.name === GIT_COMMIT_TOOL;
  const argsPath = pathFromArgs(actionRequest.args);
  const initialCommitMessage =
    typeof actionRequest.args.message === "string"
      ? (actionRequest.args.message as string)
      : "";

  const handleApprove = () => {
    onResume({
      decisions: [{ type: "approve" }],
    });
  };

  const handleReject = () => {
    if (showRejectionInput) {
      onResume({
        decisions: [
          {
            type: "reject",
            message: rejectionMessage.trim(),
          },
        ],
      });
    } else {
      setShowRejectionInput(true);
    }
  };

  const handleRejectConfirm = () => {
    onResume({
      decisions: [
        {
          type: "reject",
          message: rejectionMessage.trim(),
        },
      ],
    });
  };

  const handleEdit = () => {
    if (isEditing) {
      onResume({
        decisions: [
          {
            type: "edit",
            edited_action: {
              name: actionRequest.name,
              args: editedArgs,
            },
          },
        ],
      });
      setIsEditing(false);
      setEditedArgs({});
    }
  };

  const handleGitCommitMessageEdit = (newMessage: string) => {
    onResume({
      decisions: [
        {
          type: "edit",
          edited_action: {
            name: actionRequest.name,
            args: { ...actionRequest.args, message: newMessage },
          },
        },
      ],
    });
    setIsEditing(false);
    setEditedArgs({});
  };

  const startEditing = () => {
    setIsEditing(true);
    setEditedArgs(JSON.parse(JSON.stringify(actionRequest.args)));
    setShowRejectionInput(false);
  };

  const cancelEditing = () => {
    setIsEditing(false);
    setEditedArgs({});
  };

  const updateEditedArg = (key: string, value: string) => {
    try {
      const parsedValue =
        value.trim().startsWith("{") || value.trim().startsWith("[")
          ? JSON.parse(value)
          : value;
      setEditedArgs((prev) => ({ ...prev, [key]: parsedValue }));
    } catch {
      setEditedArgs((prev) => ({ ...prev, [key]: value }));
    }
  };

  return (
    <div className="w-full rounded-md border border-border bg-muted/30 p-4">
      {/* Header */}
      <div className="mb-3 flex items-center gap-2 text-foreground">
        <AlertCircle
          size={16}
          className="text-yellow-600 dark:text-yellow-400"
        />
        <span className="text-xs font-semibold uppercase tracking-wider">
          Approval Required
        </span>
        {isGitCommit && (
          <span className="ml-auto flex items-center gap-1 rounded-sm bg-muted px-2 py-0.5 font-mono text-xs text-muted-foreground">
            <GitCommit size={12} />
            git commit
          </span>
        )}
      </div>

      {/* Description (sem o diff — o diff é renderizado separado, abaixo) */}
      {actionRequest.description && !hasDiff && (
        <p className="mb-3 text-sm text-muted-foreground">
          {actionRequest.description}
        </p>
      )}

      {/* Diff preview (task `unified-dev-agent-task-frontend-2`) */}
      {hasDiff && actionRequest.description && (
        <DiffPreview description={actionRequest.description} />
      )}

      {/* Tool Info Card */}
      <div className="mt-4 rounded-sm border border-border bg-background p-3">
        <div className="mb-2 flex items-center gap-2">
          <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
            Tool
          </span>
          <p className="font-mono text-sm font-medium text-foreground">
            {actionRequest.name}
          </p>
          {argsPath && (
            <span className="ml-auto truncate font-mono text-xs text-muted-foreground">
              {argsPath}
            </span>
          )}
        </div>

        {/* Edit mode: editor de args JSON genérico (todas as tools) OU
            editor inline de mensagem de commit (git_commit). */}
        {isEditing ? (
          isGitCommit ? (
            <GitCommitMessageEditor
              initialMessage={initialCommitMessage}
              onConfirm={handleGitCommitMessageEdit}
              onCancel={cancelEditing}
              isLoading={isLoading}
            />
          ) : (
            <div>
              <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                Edit Arguments
              </span>
              <div className="mt-2 space-y-3">
                {Object.entries(actionRequest.args).map(([key, value]) => (
                  <div key={key}>
                    <label className="mb-1 block text-xs font-medium text-foreground">
                      {key}
                    </label>
                    <Textarea
                      value={
                        editedArgs[key] !== undefined
                          ? typeof editedArgs[key] === "string"
                            ? (editedArgs[key] as string)
                            : JSON.stringify(editedArgs[key], null, 2)
                          : typeof value === "string"
                          ? value
                          : JSON.stringify(value, null, 2)
                      }
                      onChange={(e) => updateEditedArg(key, e.target.value)}
                      className="font-mono text-xs"
                      rows={
                        typeof value === "string" && value.length < 100 ? 2 : 4
                      }
                      disabled={isLoading}
                    />
                  </div>
                ))}
              </div>
            </div>
          )
        ) : (
          /* Modo normal (não-editando): mostra args como JSON, syntax-highlighted. */
          <div>
            <div className="mb-1 flex items-center justify-between">
              <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                Arguments
              </span>
              {hasDiff && (
                <span className="font-mono text-xs text-muted-foreground">
                  full JSON below — see diff above for changes
                </span>
              )}
            </div>
            {hasDiff ? (
              // JSON cru: usa syntax highlighter para legibilidade
              <SyntaxHighlighter
                language="json"
                style={oneDark}
                customStyle={{
                  fontSize: "11px",
                  borderRadius: "2px",
                  margin: 0,
                  padding: "8px",
                  background: "rgba(127,127,127,0.06)",
                }}
                wrapLongLines
              >
                {JSON.stringify(actionRequest.args, null, 2)}
              </SyntaxHighlighter>
            ) : (
              <pre className="overflow-x-auto whitespace-pre-wrap break-all rounded-sm border border-border bg-muted/40 p-2 font-mono text-xs text-foreground">
                {JSON.stringify(actionRequest.args, null, 2)}
              </pre>
            )}
          </div>
        )}
      </div>

      {/* Rejection Message Input */}
      {showRejectionInput && !isEditing && (
        <div className="mb-4 mt-4">
          <label className="mb-2 block text-xs font-medium text-foreground">
            Rejection Message (optional)
          </label>
          <Textarea
            value={rejectionMessage}
            onChange={(e) => setRejectionMessage(e.target.value)}
            placeholder="Explain why you're rejecting this action..."
            className="text-sm"
            rows={2}
            disabled={isLoading}
          />
        </div>
      )}

      {/* Actions */}
      <div className="mt-4 flex flex-wrap gap-2">
        {isEditing ? (
          // Em edit mode, GitCommitMessageEditor já tem seus próprios botões
          // (Save / Cancel). Para outras tools, mostramos Cancel + Save & Approve.
          !isGitCommit && (
            <>
              <Button
                variant="outline"
                size="sm"
                onClick={cancelEditing}
                disabled={isLoading}
              >
                Cancel
              </Button>
              <Button
                size="sm"
                onClick={handleEdit}
                disabled={isLoading}
                className="bg-green-600 text-white hover:bg-green-700 dark:bg-green-600 dark:hover:bg-green-700"
              >
                <Check size={14} />
                {isLoading ? "Saving..." : "Save & Approve"}
              </Button>
            </>
          )
        ) : showRejectionInput ? (
          <>
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                setShowRejectionInput(false);
                setRejectionMessage("");
              }}
              disabled={isLoading}
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              size="sm"
              onClick={handleRejectConfirm}
              disabled={isLoading}
            >
              {isLoading ? "Rejecting..." : "Confirm Reject"}
            </Button>
          </>
        ) : (
          <>
            {allowedDecisions.includes("reject") && (
              <Button
                variant="outline"
                size="sm"
                onClick={handleReject}
                disabled={isLoading}
                className="text-destructive hover:bg-destructive/10"
              >
                <X size={14} />
                Reject
              </Button>
            )}
            {allowedDecisions.includes("edit") && (
              <Button
                variant="outline"
                size="sm"
                onClick={startEditing}
                disabled={isLoading}
              >
                <Pencil size={14} />
                {isGitCommit ? "Edit Message" : "Edit"}
              </Button>
            )}
            {allowedDecisions.includes("approve") && (
              <Button
                size="sm"
                onClick={handleApprove}
                disabled={isLoading}
                className={cn(
                  "bg-green-600 text-white hover:bg-green-700",
                  "dark:bg-green-600 dark:hover:bg-green-700"
                )}
              >
                <Check size={14} />
                {isLoading ? "Approving..." : "Approve"}
              </Button>
            )}
          </>
        )}
      </div>
    </div>
  );
}
