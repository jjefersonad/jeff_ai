"use client";

/**
 * Modal that lists every available assistant and lets the user pick one for
 * the current thread.
 *
 * Today the catalog is a single static entry (`unified` — see design decision
 * D6 in `frontend-menu-redesign-design`). When more assistants are wired in
 * the backend, replace the static `ASSISTANTS` array with a fetch against
 * the future `GET /api/assistants` endpoint; the component contract does not
 * change.
 *
 * Accessibility:
 *   - `Dialog` from `@radix-ui/react-dialog` provides `role="dialog"`,
 *     `aria-modal="true"`, focus trap while open, and `Esc` to dismiss.
 *   - Focus is moved to the dialog content on open and returned to the
 *     trigger on close (Radix behaviour).
 *   - `aria-checked` is set on the selected row so screen readers announce
 *     the current selection.
 */

import { Check } from "lucide-react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

export interface Assistant {
  id: string;
  name: string;
  description: string;
}

const ASSISTANTS: readonly Assistant[] = [
  {
    id: "unified",
    name: "Unified",
    description: "Default Jeff AI assistant — code, research, and chat.",
  },
];

interface AssistantModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  currentAssistantId: string;
  onSelect: (assistantId: string) => void;
}

export function AssistantModal({
  open,
  onOpenChange,
  currentAssistantId,
  onSelect,
}: AssistantModalProps) {
  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
    >
      <DialogContent className="sm:max-w-[480px]">
        <DialogHeader>
          <DialogTitle>Choose assistant</DialogTitle>
          <DialogDescription>
            Pick the assistant for this thread. Today only <b>Unified</b> is
            available; more assistants are coming.
          </DialogDescription>
        </DialogHeader>
        <ul
          role="listbox"
          aria-label="Available assistants"
          className="flex flex-col gap-1"
        >
          {ASSISTANTS.map((assistant) => {
            const selected = assistant.id === currentAssistantId;
            return (
              <li key={assistant.id}>
                <button
                  type="button"
                  role="option"
                  aria-selected={selected}
                  aria-checked={selected}
                  onClick={() => onSelect(assistant.id)}
                  className={cn(
                    "flex w-full items-start gap-3 rounded-md border border-transparent p-3 text-left text-sm transition-colors",
                    "hover:bg-accent hover:text-accent-foreground",
                    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                    selected && "border-primary bg-primary/5"
                  )}
                >
                  <span
                    aria-hidden="true"
                    className={cn(
                      "mt-0.5 flex h-5 w-5 items-center justify-center rounded-full border",
                      selected
                        ? "border-primary bg-primary text-primary-foreground"
                        : "border-muted-foreground/30"
                    )}
                  >
                    {selected ? <Check className="h-3 w-3" /> : null}
                  </span>
                  <span className="flex min-w-0 flex-col">
                    <span className="font-medium">{assistant.name}</span>
                    <span className="text-muted-foreground">
                      {assistant.description}
                    </span>
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      </DialogContent>
    </Dialog>
  );
}
