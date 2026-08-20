"use client";

/**
 * Primary navigation sidebar for the authenticated layout.
 *
 * Renders **Conversas**, **Imagens**, **Servidores MCP**, **Integrações**,
 * **Agendamentos**, **Perfis de agente**, **CRM**, **E-mail**, and (for
 * `role=admin` only) **Consumo** and **Usuários** — linking to `/`, `/images`,
 * `/mcp-servers`, `/integrations`, `/scheduling`, `/agent-profiles`, `/crm`,
 * `/email`, `/usage`, and `/admin/users`.
 * **Conversas** exists because the top-bar "JEFF AI" link back to `/` isn't an
 * obvious return path once a user has navigated into a full sidebar
 * destination. The active entry (matching the current pathname) is
 * highlighted with `aria-current="page"`. Admin-only **Consumo** is
 * filtered via `getVisibleNavEntries(user?.role)` (token-usage-reporting
 * REQ-006). Admin-only **Usuários** is filtered through the same gate
 * (user-management-ui REQ-005, frontend-5) — the entry is registered with
 * `requireRole: "admin"` so non-admin users never see the link, matching
 * the design decision that hiding it client-side is enough since
 * `useAuth().user.role` is the same role the backend's `require_admin`
 * enforces.
 *
 * Responsive behaviour (per design decision D4):
 *   - ≥ 768px viewport → the sidebar renders as an inline panel that pushes
 *     the main content to the right. The `?sidebar=` thread-history panel
 *     keeps its `ResizablePanel`; the two coexist side-by-side.
 *   - < 768px viewport → the sidebar renders as an overlay drawer with a
 *     dim backdrop. A backdrop click or `Esc` closes it. This avoids
 *     shrinking the chat composer on small screens.
 *
 * Persistence is owned by `<NavSidebarProvider />` via the
 * `localStorage["jeff_ai.nav.open"]` key — distinct from the thread-history
 * `?sidebar=` query state (left untouched by this component).
 */

import { useEffect, useMemo } from "react";
import { usePathname } from "next/navigation";
import { XIcon } from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { useNavSidebar } from "@/app/components/NavSidebarProvider";
import { useIsMobile } from "@/app/hooks/useIsMobile";
import { useEscToClose } from "@/app/hooks/useEscToClose";
import {
  getVisibleNavEntries,
  NAV_ENTRIES,
  type NavEntry,
} from "@/app/components/navEntries";
import { useAuth } from "@/providers/AuthProvider";

const SIDEBAR_HEADER = "Menu";

export function NavSidebar() {
  const pathname = usePathname();
  const { open, setOpen, hydrated } = useNavSidebar();
  const { user, isRehydrating } = useAuth();
  // While `/api/me` is in flight and we have no role yet, keep every entry
  // visible — filtering on `null` would hide admin items (Consumo/Usuários)
  // and make them "disappear" during navigation/remount. Pages still enforce
  // `require_admin` server-side.
  const entries = useMemo(() => {
    if (isRehydrating && !user) {
      return [...NAV_ENTRIES];
    }
    return getVisibleNavEntries(user?.role);
  }, [user, isRehydrating]);
  const isMobile = useIsMobile();
  const close = () => setOpen(false);

  // Only honour `Esc` on the mobile overlay — on desktop the sidebar is a
  // persistent push panel, so `Esc` should not close it.
  useEscToClose(open && isMobile, close);

  // On mobile, an open overlay should not be reachable by `Tab` outside the
  // sidebar. The `Nav` element's focus is managed implicitly by the
  // browser; we just need to bring focus inside when the overlay opens so
  // the first link is the next `Tab` stop.
  useEffect(() => {
    if (!open || !isMobile) return;
    if (typeof document === "undefined") return;
    const firstLink = document.querySelector<HTMLAnchorElement>(
      "#jeff-ai-primary-nav a[href]"
    );
    firstLink?.focus();
  }, [open, isMobile]);

  // Before hydration, render nothing to avoid showing the desktop panel
  // for a split-second on a mobile device (the storage value would
  // otherwise pop in after mount).
  if (!hydrated) {
    return null;
  }

  if (!open) {
    return null;
  }

  if (isMobile) {
    return (
      <>
        <div
          aria-hidden="true"
          onClick={close}
          className="fixed inset-0 z-40 bg-black/50"
        />
        <nav
          id="jeff-ai-primary-nav"
          aria-label="Primary"
          data-testid="nav-sidebar"
          className={cn(
            "fixed inset-y-0 left-0 z-50 flex w-72 flex-col gap-2 border-r border-border bg-background p-4 shadow-lg"
          )}
        >
          <div className="flex items-center justify-between">
            <span className="text-sm font-semibold">{SIDEBAR_HEADER}</span>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              onClick={close}
              aria-label="Close navigation"
            >
              <XIcon aria-hidden="true" />
            </Button>
          </div>
          <ul className="flex flex-col gap-1">
            {entries.map((entry) => (
              <li key={entry.href}>
                <SidebarLink
                  entry={entry}
                  active={entry.match(pathname ?? "")}
                  onNavigate={close}
                />
              </li>
            ))}
          </ul>
        </nav>
      </>
    );
  }

  // Desktop: inline panel that pushes the main content (no overlay).
  return (
    <nav
      id="jeff-ai-primary-nav"
      aria-label="Primary"
      data-testid="nav-sidebar"
      className="flex w-60 shrink-0 flex-col gap-2 border-r border-border bg-card p-4"
    >
      <span className="text-sm font-semibold">{SIDEBAR_HEADER}</span>
      <ul className="flex flex-col gap-1">
        {entries.map((entry) => (
          <li key={entry.href}>
            <SidebarLink
              entry={entry}
              active={entry.match(pathname ?? "")}
            />
          </li>
        ))}
      </ul>
    </nav>
  );
}

function SidebarLink({
  entry,
  active,
  onNavigate,
}: {
  entry: NavEntry;
  active: boolean;
  onNavigate?: () => void;
}) {
  const Icon = entry.icon;
  return (
    <a
      href={entry.href}
      onClick={onNavigate}
      aria-current={active ? "page" : undefined}
      className={cn(
        "flex items-start gap-3 rounded-md p-2 text-sm transition-colors text-on-surface",
        "hover:bg-accent hover:text-on-surface",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        active && "bg-accent text-on-surface"
      )}
    >
      <Icon aria-hidden="true" className="mt-0.5 text-on-surface" />
      <span className="flex min-w-0 flex-col">
        <span className="font-medium text-on-surface">{entry.label}</span>
        <span className="text-xs text-muted-foreground">
          {entry.description}
        </span>
      </span>
    </a>
  );
}
