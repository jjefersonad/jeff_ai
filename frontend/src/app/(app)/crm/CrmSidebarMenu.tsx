"use client";

/**
 * Lateral menu listing the CRM sections (Contatos, Empresas, Funil).
 * Presentational only — the responsive wrapper (mobile overlay vs desktop
 * `ResizablePanel`) and the `crmMenu` open/closed state live in
 * `crm/page.tsx` (design D4 of `crm-lateral-menu-design`).
 */

import { cn } from "@/lib/utils";
import type { CrmUiTab } from "@/lib/crm";

const ENTRIES: { tab: CrmUiTab; label: string }[] = [
  { tab: "contacts", label: "Contatos" },
  { tab: "companies", label: "Empresas" },
  { tab: "pipeline", label: "Funil" },
];

export function CrmSidebarMenu({
  active,
  onSelect,
}: {
  active: CrmUiTab;
  onSelect: (tab: CrmUiTab) => void;
}) {
  return (
    <nav aria-label="Seções do CRM">
      <ul className="flex flex-col gap-1">
        {ENTRIES.map((entry) => {
          const isActive = entry.tab === active;
          return (
            <li key={entry.tab}>
              <button
                type="button"
                aria-current={isActive ? "true" : undefined}
                onClick={() => onSelect(entry.tab)}
                className={cn(
                  "w-full rounded-md p-2 text-left text-sm transition-colors text-on-surface",
                  "hover:bg-accent hover:text-on-surface",
                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                  isActive && "bg-accent text-on-surface"
                )}
              >
                {entry.label}
              </button>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
