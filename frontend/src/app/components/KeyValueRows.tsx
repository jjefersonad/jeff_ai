"use client";

import { useState } from "react";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Plus, Trash2 } from "lucide-react";

interface KeyValueRow {
  key: string;
  varName: string;
}

interface KeyValueRowsProps {
  label: string;
  emptyHint: string;
  keyPlaceholder: string;
  valuePlaceholder: string;
  /**
   * Initial rows when the parent decides to override the empty default
   * (e.g. seeding from an `editing` server summary). Changes from the
   * parent are ignored after mount — the input is owned by the user
   * via add/remove/edit.
   */
  initial?: Record<string, string>;
  onChange?: (value: Record<string, string>) => void;
}

function rowsFromRecord(record: Record<string, string>): KeyValueRow[] {
  return Object.entries(record).map(([key, varName]) => ({ key, varName }));
}

function recordsFromRows(rows: KeyValueRow[]): Record<string, string> {
  const out: Record<string, string> = {};
  for (const row of rows) {
    const k = row.key.trim();
    if (!k) continue;
    out[k] = row.varName.trim();
  }
  return out;
}

/**
 * Reusable pair-of-inputs editor for "key → ${ENV_VAR_NAME}" lookups used
 * by the MCP admin dialog (env vars for `stdio`, headers for `http`).
 * Same shape on both sides of that map: a server-side identifier mapped
 * to a name from `backend/.env` — the actual secret is never on the wire.
 *
 * Behavior:
 * - `initial` seeds the rows **only at mount** (via `useState` initializer).
 *   To swap the rows when a different server is loaded into the same
 *   dialog instance, pass a `key` from the parent that changes between
 *   servers — React reconciliation will remount the component and the
 *   new `initial` will be picked up.
 * - `onChange` fires on every add / remove / edit (debounce is not used;
 *   in this dialog the rows are short enough that the cost is trivial).
 *   The value handed back is a `Record<string, string>` already trimmed
 *   of rows with empty keys — i.e. the exact shape the backend wants.
 */
export function KeyValueRows({
  label,
  emptyHint,
  keyPlaceholder,
  valuePlaceholder,
  initial = {},
  onChange,
}: KeyValueRowsProps) {
  const [rows, setRows] = useState<KeyValueRow[]>(() =>
    rowsFromRecord(initial)
  );

  const update = (next: KeyValueRow[]) => {
    setRows(next);
    onChange?.(recordsFromRows(next));
  };

  const add = () => update([...rows, { key: "", varName: "" }]);
  const remove = (index: number) =>
    update(rows.filter((_, i) => i !== index));
  const edit = (index: number, field: keyof KeyValueRow, value: string) =>
    update(
      rows.map((row, i) => (i === index ? { ...row, [field]: value } : row))
    );

  return (
    <div className="grid gap-2">
      <div className="flex items-center justify-between">
        <Label>{label}</Label>
        <button
          type="button"
          onClick={add}
          className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
        >
          <Plus className="h-3 w-3" />
          Adicionar
        </button>
      </div>
      {rows.length === 0 && (
        <p className="text-xs text-muted-foreground">{emptyHint}</p>
      )}
      {rows.map((row, index) => (
        <div key={index} className="flex items-center gap-2">
          <Input
            placeholder={keyPlaceholder}
            value={row.key}
            onChange={(e) => edit(index, "key", e.target.value)}
          />
          <Input
            placeholder={valuePlaceholder}
            value={row.varName}
            onChange={(e) => edit(index, "varName", e.target.value)}
          />
          <button
            type="button"
            onClick={() => remove(index)}
            className="shrink-0 text-muted-foreground hover:text-destructive"
            aria-label="Remover"
          >
            <Trash2 className="h-4 w-4" />
          </button>
        </div>
      ))}
    </div>
  );
}
