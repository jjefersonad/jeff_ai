"use client";

/**
 * Authenticated shell layout for the Next.js App Router `(app)` route group.
 *
 * Per the post-verify fix in `frontend-menu-redesign-task-verify-fix-1`,
 * the shell (top bar + left navigation sidebar + `NavSidebarProvider`)
 * used to live only inside `app/page.tsx` (the chat route), which meant
 * that `/images`, `/mcp-servers`, and `/usage` had no top bar and no way
 * back to the chat. This layout extracts the shell so that every
 * authenticated route inside `(app)/` renders it.
 *
 * The shell is NOT gated on `useAuth().isAuthenticated` here. That flag
 * starts `false` and is filled by the mount-time `GET /api/me` probe in
 * `AuthProvider` (or by an in-session `login()`). On a cold load it is
 * briefly `false` even for a fully authenticated user, which would hide the
 * hamburger/sidebar/user-menu if we gated here. Gating is unnecessary anyway:
 * `(app)/layout.tsx` sits outside `/public/*`, which `frontend/src/middleware.ts`
 * always gates on the session cookie before this layout ever renders — so by
 * the time we get here, the request has already been authenticated.
 * `UserMenu` still self-gates on `user` internally (per `frontend-user-menu-spec`
 * REQ-001 "User opens the menu while unauthenticated"), so its avatar simply
 * waits for rehydration rather than the whole shell disappearing.
 *
 * Per-page affordances (the `Conversas` thread-history toggle, the
 * `Nova conversa` button, the `+ Adicionar servidor` action on `/mcp-servers`,
 * etc.) live inside each page's own JSX, not in this shell. The shell
 * owns the chrome only.
 */

import Link from "next/link";
import { SidebarToggle } from "@/app/components/SidebarToggle";
import { UserMenu } from "@/app/components/UserMenu";
import { NavSidebar } from "@/app/components/NavSidebar";
import { NavSidebarProvider } from "@/app/components/NavSidebarProvider";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <NavSidebarProvider>
      <div className="flex h-screen flex-col">
        <header className="flex h-16 items-center justify-between border-b border-border px-6">
          <div className="flex items-center gap-4">
            <SidebarToggle />
            <Link
              href="/"
              className="text-on-surface text-xl font-semibold hover:opacity-80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-sm"
              aria-label="JEFF"
            >
              JEFF
            </Link>
          </div>
          <div className="flex items-center gap-2">
            <UserMenu />
          </div>
        </header>
        <div className="flex flex-1 overflow-hidden">
          <NavSidebar />
          {/* `overflow-y-auto` (not `overflow-hidden`): the chat route already
              clips and scrolls its own content internally (see the
              `overflow-hidden` around the resizable panels in
              `(app)/page.tsx`), but `/images` and `/mcp-servers` are normal
              `min-h-screen` pages that need this region to scroll — with
              `overflow-hidden` here, any content past the viewport (extra
              images, pagination controls) was clipped with no way to reach
              it. */}
          <div className="flex-1 overflow-y-auto">{children}</div>
        </div>
      </div>
    </NavSidebarProvider>
  );
}
