"use client";

/**
 * Primary navigation sidebar for the authenticated layout.
 *
 * Renders three entries — **Chat**, **Images**, and **MCP Servers** — linking
 * to `/`, `/images`, and `/mcp-servers` respectively. **Chat** exists because
 * the top-bar "JEFF AI" link back to `/` isn't an obvious return path once a
 * user has navigated into a full sidebar destination. The active entry
 * (matching the current pathname) is highlighted with `aria-current="page"`.
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

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { ImageIcon, MessagesSquare, Plug, XIcon } from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { useNavSidebar } from "@/app/components/NavSidebarProvider";

interface NavEntry {
  label: string;
  href: string;
  description: string;
  // Loose icon type: every lucide icon accepts `aria-hidden` (string | boolean
  // in JSX) and `className` (string). Using `React.ComponentType<any>` here
  // is the same approach the rest of the codebase uses for icons — see
  // e.g. `frontend/src/app/page.tsx` passing icon components as children.
  icon: React.ComponentType<Record<string, unknown>>;
  match: (pathname: string) => boolean;
}

const ENTRIES: readonly NavEntry[] = [
  {
    label: "Chat",
    href: "/",
    description: "Back to the conversation",
    icon: MessagesSquare,
    // Only the exact root route — nested routes belong to other entries.
    match: (p) => p === "/",
  },
  {
    label: "Images",
    href: "/images",
    description: "Browse generated and reference images",
    icon: ImageIcon,
    // Match `/images` and any nested route (`/images/abc`).
    match: (p) => p === "/images" || p.startsWith("/images/"),
  },
  {
    label: "MCP Servers",
    href: "/mcp-servers",
    description: "Manage Model Context Protocol servers",
    icon: Plug,
    match: (p) => p === "/mcp-servers" || p.startsWith("/mcp-servers/"),
  },
];

const MOBILE_BREAKPOINT = 768; // px — see D4 of the design.

function useIsMobile(): boolean {
  // SSR-safe: starts `false` (desktop) on both server and client, then
  // syncs to the real value in the effect. This avoids hydration mismatch
  // and keeps the desktop default behaviour during the first paint.
  const [isMobile, setIsMobile] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const mql = window.matchMedia(`(max-width: ${MOBILE_BREAKPOINT - 1}px)`);
    const onChange = (event: MediaQueryListEvent) => {
      setIsMobile(event.matches);
    };
    setIsMobile(mql.matches);
    mql.addEventListener("change", onChange);
    return () => {
      mql.removeEventListener("change", onChange);
    };
  }, []);

  return isMobile;
}

/**
 * Close the sidebar on `Esc`. Only attached when the sidebar is open and the
 * viewport is below the mobile breakpoint (where the sidebar is an overlay
 * and the user expects keyboard dismissal). On desktop the sidebar is a
 * persistent push panel, so `Esc` should not close it.
 */
function useEscToClose(enabled: boolean, onClose: () => void) {
  useEffect(() => {
    if (!enabled) return;
    if (typeof window === "undefined") return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [enabled, onClose]);
}

export function NavSidebar() {
  const pathname = usePathname();
  const { open, setOpen, hydrated } = useNavSidebar();
  const isMobile = useIsMobile();
  const close = () => setOpen(false);

  // Only honour `Esc` on the mobile overlay (see docstring above).
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
            <span className="text-sm font-semibold">Navigation</span>
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
            {ENTRIES.map((entry) => (
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
      <span className="text-sm font-semibold">Navigation</span>
      <ul className="flex flex-col gap-1">
        {ENTRIES.map((entry) => (
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
        "flex items-start gap-3 rounded-md p-2 text-sm transition-colors text-white",
        "hover:bg-accent hover:text-white",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        active && "bg-accent text-white"
      )}
    >
      <Icon aria-hidden="true" className="mt-0.5 text-white" />
      <span className="flex min-w-0 flex-col">
        <span className="font-medium text-white">{entry.label}</span>
        <span className="text-xs text-muted-foreground">
          {entry.description}
        </span>
      </span>
    </a>
  );
}
