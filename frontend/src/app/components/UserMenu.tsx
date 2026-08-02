"use client";

/**
 * User menu (avatar + dropdown) for the top bar.
 *
 * Per `frontend-menu-redesign` / `frontend-user-menu-spec` REQ-001, the menu
 * contains exactly two rows in DOM order:
 *   1. A non-interactive identity row (username + role).
 *   2. The `Sign out` action — the **last** item in the list.
 *
 * The previous `Settings` button, the `LangSmith` key form, and the
 * top-bar sign-out button are no longer accessible from here (the old
 * `ConfigDialog` and `LogoutButton` files were deleted in `wiring-4`). The
 * `Sign out` action calls `useAuth().logout()` from
 * `frontend/src/providers/AuthProvider.tsx`, which posts to `/public/logout`
 * (revokes the session server-side) and redirects to `/public/login`.
 *
 * The dropdown is rendered only when `useAuth().isAuthenticated === true`;
 * otherwise the avatar trigger is hidden (login flow is the only affordance,
 * per REQ-001 Scenario "User opens the menu while unauthenticated").
 *
 * Keyboard / a11y: Radix's `DropdownMenu` provides focus management, `Esc`
 * to close, type-ahead, and the `aria-haspopup` / `aria-expanded` semantics
 * on the trigger. The trigger's accessible name includes the username.
 */

import { LogOut, UserRound } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useAuth } from "@/providers/AuthProvider";

function initialsFor(username: string): string {
  // Take the first character of the first word, uppercased. Falls back to
  // "?" for empty strings (defensive — the backend should not produce
  // empty usernames, but the UI must not crash if it does).
  const first = username.trim().charAt(0);
  return (first || "?").toUpperCase();
}

export function UserMenu() {
  const { isAuthenticated, isAuthenticating, user, logout } = useAuth();

  // Per REQ-001: render nothing when unauthenticated. The login flow is the
  // only affordance on those pages.
  if (!isAuthenticated || !user) {
    return null;
  }

  const handleSignOut = () => {
    void logout();
  };

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          aria-label={`Open user menu for ${user.username}`}
          title={user.username}
        >
          <span
            aria-hidden="true"
            className="flex h-7 w-7 items-center justify-center rounded-full bg-primary text-xs font-semibold text-primary-foreground"
          >
            {initialsFor(user.username)}
          </span>
          <span className="sr-only">
            <UserRound aria-hidden="true" />
            {user.username}
          </span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent
        align="end"
        sideOffset={8}
        className="min-w-[200px]"
      >
        <DropdownMenuLabel className="flex flex-col gap-0.5">
          <span className="text-sm font-medium">{user.username}</span>
          <span className="text-xs font-normal text-muted-foreground">
            Role: {user.role}
          </span>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem
          onSelect={(event) => {
            // We do the navigation in `handleSignOut`; prevent Radix from
            // closing the menu before the async logout resolves, so the
            // user sees a stable state until the redirect lands.
            event.preventDefault();
            handleSignOut();
          }}
          disabled={isAuthenticating}
          className="text-destructive focus:text-destructive"
        >
          <LogOut aria-hidden="true" />
          <span>{isAuthenticating ? "Signing out…" : "Sign out"}</span>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
