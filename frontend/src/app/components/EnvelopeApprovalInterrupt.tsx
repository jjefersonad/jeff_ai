"use client";

import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { AlertTriangle, ShieldQuestion, X, Check } from "lucide-react";
import type {
  EnvelopeGrantDecision,
  EnvelopeProposalInterruptData,
} from "@/app/types/types";
import { cn } from "@/lib/utils";

interface EnvelopeApprovalInterruptProps {
  envelope: EnvelopeProposalInterruptData;
  onResume: (decision: EnvelopeGrantDecision) => void;
  isLoading?: boolean;
}

/**
 * Human-readable label per capability. Mirrors
 * `src/agents/unified/effects.py:Capability` on the backend.
 */
const CAPABILITY_LABELS: Record<string, string> = {
  read: "Read files / search",
  write_new: "Create new files",
  write_existing: "Edit existing files",
  vcs: "Git (commit, branch)",
  shell: "Run shell commands",
  network: "Network access",
  unknown: "Unrecognized tool (MCP third-party)",
};

function capabilityLabel(capability: string): string {
  return CAPABILITY_LABELS[capability] ?? capability;
}

/**
 * Approval UI for the envelope proposed by `propose_envelope_tool`. This is
 * the single most consequential piece of UI in the harness (task
 * `envelope-6`): if it takes more than a few seconds to read, or asks for
 * approval more than once per task, the whole permission model degrades
 * into "approve everything" muscle memory within weeks — see risk R1 in the
 * `unified-agent-realignment` design.
 *
 * Toggling a capability off before granting IS the "edit" action — there is
 * no separate edit mode, unlike `ToolApprovalInterrupt`'s JSON-arg editor.
 * A capability-selection model doesn't need free-text editing, and fewer
 * clicks means less approval fatigue.
 */
export function EnvelopeApprovalInterrupt({
  envelope,
  onResume,
  isLoading,
}: EnvelopeApprovalInterruptProps) {
  const requiredCapabilities = envelope.proposal.required_capabilities;
  const excludedCapabilities = envelope.proposal.excluded_capabilities;

  const originalSet = useMemo(
    () => new Set(requiredCapabilities.map((c) => c.capability)),
    [requiredCapabilities]
  );
  const [selected, setSelected] = useState<Set<string>>(
    () => new Set(originalSet)
  );

  const toggleCapability = (capability: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(capability)) {
        next.delete(capability);
      } else {
        next.add(capability);
      }
      return next;
    });
  };

  const setsAreEqual = (a: Set<string>, b: Set<string>) =>
    a.size === b.size && Array.from(a).every((v) => b.has(v));

  const handleGrant = () => {
    const grantedCapabilities = Array.from(selected);
    onResume({
      granted_capabilities: grantedCapabilities,
      edited: !setsAreEqual(selected, originalSet),
      rejected: false,
    });
  };

  const handleDeny = () => {
    onResume({ granted_capabilities: [], edited: false, rejected: true });
  };

  return (
    <div className="w-full rounded-md border border-border bg-muted/30 p-4">
      {/* Header */}
      <div className="mb-3 flex items-center gap-2 text-foreground">
        <ShieldQuestion
          size={16}
          className="text-yellow-600 dark:text-yellow-400"
        />
        <span className="text-xs font-semibold uppercase tracking-wider">
          Permission Request
        </span>
      </div>

      {/* Contradiction warning (D4) — shown WITH PROMINENCE, not a footnote */}
      {envelope.contradiction_warning && (
        <div className="mb-4 flex items-start gap-2 rounded-sm border border-destructive/50 bg-destructive/10 p-3">
          <AlertTriangle
            size={16}
            className="mt-0.5 shrink-0 text-destructive"
          />
          <p className="text-sm text-destructive">
            {envelope.contradiction_warning}
          </p>
        </div>
      )}

      {/* Required capabilities — toggleable */}
      <div className="mb-4 rounded-sm border border-border bg-background p-3">
        <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
          Requested for this task
        </span>
        <div className="mt-2 space-y-3">
          {requiredCapabilities.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              (nothing requested — this task only needs read/search)
            </p>
          ) : (
            requiredCapabilities.map((cap) => (
              <div
                key={cap.capability}
                className="flex items-start justify-between gap-3"
              >
                <div className="min-w-0">
                  <p className="text-sm font-medium text-foreground">
                    {capabilityLabel(cap.capability)}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {cap.justification}
                  </p>
                </div>
                <Switch
                  checked={selected.has(cap.capability)}
                  onCheckedChange={() => toggleCapability(cap.capability)}
                  disabled={isLoading}
                  className="mt-0.5 shrink-0"
                />
              </div>
            ))
          )}
        </div>
      </div>

      {/* Explicitly excluded capabilities — informational, not toggleable */}
      {excludedCapabilities.length > 0 && (
        <div className="mb-4">
          <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
            Explicitly not requested
          </span>
          <p className="mt-1 text-xs text-muted-foreground">
            {excludedCapabilities.map(capabilityLabel).join(", ")}
          </p>
        </div>
      )}

      {/* Actions */}
      <div className="flex flex-wrap gap-2">
        <Button
          variant="outline"
          size="sm"
          onClick={handleDeny}
          disabled={isLoading}
          className="text-destructive hover:bg-destructive/10"
        >
          <X size={14} />
          Deny
        </Button>
        <Button
          size="sm"
          onClick={handleGrant}
          disabled={isLoading}
          className={cn(
            "bg-green-600 text-white hover:bg-green-700",
            "dark:bg-green-600 dark:hover:bg-green-700"
          )}
        >
          <Check size={14} />
          {isLoading
            ? "Granting..."
            : selected.size === 0
              ? "Grant (none selected)"
              : "Grant"}
        </Button>
      </div>
    </div>
  );
}
