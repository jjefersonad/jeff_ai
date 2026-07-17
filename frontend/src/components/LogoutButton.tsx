"use client";

/**
 * Logout button for the Jeff AI frontend.
 *
 * Wraps `AuthProvider.logout()` (REQ-005 of `frontend-route-guard`):
 *   1. POST /public/logout — the backend revokes the session row and clears
 *      the httpOnly cookie. The call is best-effort: if the backend is down
 *      or the cookie is already gone, the user still gets bounced to the
 *      login page (the original `AuthProvider.logout` swallows network errors
 *      on purpose).
 *   2. Local `user` state is reset to `null`, flipping `isAuthenticated` to
 *      `false`.
 *   3. Navigation to `/public/login` is performed via `router.replace` so the
 *      protected page doesn't end up in the browser history.
 *
 * The button is disabled while the request is in flight to avoid double
 * submissions.
 */

import { LogOut } from "lucide-react";

import { useAuth } from "@/providers/AuthProvider";
import { Button } from "@/components/ui/button";

export function LogoutButton() {
  const { logout, isAuthenticating } = useAuth();

  return (
    <Button
      variant="outline"
      size="sm"
      onClick={() => {
        void logout();
      }}
      disabled={isAuthenticating}
    >
      <LogOut className="h-4 w-4" />
      {isAuthenticating ? "Signing out…" : "Sign out"}
    </Button>
  );
}
