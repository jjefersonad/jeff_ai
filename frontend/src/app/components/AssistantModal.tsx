"use client";

/**
 * Modal that lists the authenticated user's agent profiles and lets them
 * pick one for the current thread.
 *
 * The catalog comes from `GET /api/agent-profiles` — not from a static
 * graph-id list. Selecting a row yields the profile UUID (`profileId`);
 * the LangGraph graph id (`assistantId` / `unified`) is unchanged.
 *
 * Accessibility:
 *   - `Dialog` from `@radix-ui/react-dialog` provides `role="dialog"`,
 *     `aria-modal="true"`, focus trap while open, and `Esc` to dismiss.
 *   - Focus is moved to the dialog content on open and returned to the
 *     trigger on close (Radix behaviour).
 *   - `aria-checked` is set on the selected row so screen readers announce
 *     the current selection.
 */

import { useEffect, useState } from "react";
import { Check } from "lucide-react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";
import {
  listAgentProfiles,
  type AgentProfile,
} from "@/lib/agent-profiles";

interface AssistantModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  currentProfileId?: string;
  onSelect: (profileId: string) => void;
}

export function AssistantModal({
  open,
  onOpenChange,
  currentProfileId,
  onSelect,
}: AssistantModalProps) {
  const [profiles, setProfiles] = useState<AgentProfile[]>([]);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    listAgentProfiles().then((rows) => {
      if (!cancelled) setProfiles(rows);
    });
    return () => {
      cancelled = true;
    };
  }, [open]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[480px]">
        <DialogHeader>
          <DialogTitle>Escolher agente</DialogTitle>
          <DialogDescription>
            Escolha o perfil para as próximas mensagens. O grafo continua{" "}
            <b>unified</b>.
          </DialogDescription>
        </DialogHeader>
        {profiles.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Nenhum perfil cadastrado. O chat usa o agente padrão, sem inventar
            um id de perfil.
          </p>
        ) : (
          <ul
            role="listbox"
            aria-label="Perfis disponíveis"
            className="flex flex-col gap-1"
          >
            <li>
              <button
                type="button"
                role="option"
                aria-selected={!currentProfileId}
                aria-checked={!currentProfileId}
                onClick={() => onSelect("")}
                className={cn(
                  "flex w-full items-start gap-3 rounded-md border border-transparent p-3 text-left text-sm transition-colors",
                  "hover:bg-accent hover:text-accent-foreground",
                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                  !currentProfileId && "border-primary bg-primary/5"
                )}
              >
                <span
                  aria-hidden="true"
                  className={cn(
                    "mt-0.5 flex h-5 w-5 items-center justify-center rounded-full border",
                    !currentProfileId
                      ? "border-primary bg-primary text-primary-foreground"
                      : "border-muted-foreground/30"
                  )}
                >
                  {!currentProfileId ? <Check className="h-3 w-3" /> : null}
                </span>
                <span className="flex min-w-0 flex-col">
                  <span className="font-medium">Agente padrão</span>
                  <span className="text-muted-foreground">(padrão unified)</span>
                </span>
              </button>
            </li>
            {profiles.map((profile) => {
              const selected = profile.id === currentProfileId;
              return (
                <li key={profile.id}>
                  <button
                    type="button"
                    role="option"
                    aria-selected={selected}
                    aria-checked={selected}
                    onClick={() => onSelect(profile.id)}
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
                      <span className="font-medium">{profile.name}</span>
                      <span className="text-muted-foreground">{profile.slug}</span>
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </DialogContent>
    </Dialog>
  );
}
