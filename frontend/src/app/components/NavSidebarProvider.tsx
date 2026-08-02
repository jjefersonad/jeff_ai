"use client";

/**
 * Provider + hook for the navigation sidebar open/closed state.
 *
 * State is persisted in `localStorage["jeff_ai.nav.open"]` (per design
 * decision D3 of `frontend-menu-redesign-design`). This storage key is
 * **intentionally distinct** from the thread-history `?sidebar=` query
 * state used by `useQueryState("sidebar")` in `frontend/src/app/page.tsx`
 * — the two surfaces are independent and must not share a key.
 *
 * SSR-safe: the initial value is read in a `useEffect` after mount so the
 * server-rendered HTML always reports the sidebar as closed (matching the
 * default). This avoids hydration mismatches and is the behaviour required
 * by `left-sidebar-navigation-spec` REQ-003.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

const STORAGE_KEY = "jeff_ai.nav.open";

interface NavSidebarContextValue {
  open: boolean;
  /**
   * True after the first `useEffect` has hydrated the state from
   * `localStorage`. Until then the sidebar renders in the default-closed
   * state. Consumers that need to avoid a flash of the default state can
   * gate on this flag.
   */
  hydrated: boolean;
  setOpen: (open: boolean) => void;
  toggle: () => void;
}

const NavSidebarContext = createContext<NavSidebarContextValue | null>(null);

export function NavSidebarProvider({ children }: { children: ReactNode }) {
  // Start closed on both server and client to avoid hydration mismatches.
  // The real value from `localStorage` is applied in the effect below.
  const [open, setOpenState] = useState(false);
  const [hydrated, setHydrated] = useState(false);

  // Hydrate from `localStorage` exactly once after mount.
  useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      const stored = window.localStorage.getItem(STORAGE_KEY);
      if (stored === "1") {
        setOpenState(true);
      }
    } catch {
      // Ignore: storage may be unavailable (private mode, etc.) — fall back
      // to the default-closed state.
    }
    setHydrated(true);
  }, []);

  const setOpen = useCallback((next: boolean) => {
    setOpenState(next);
    if (typeof window !== "undefined") {
      try {
        window.localStorage.setItem(STORAGE_KEY, next ? "1" : "0");
      } catch {
        // Same rationale as above — best-effort persistence.
      }
    }
  }, []);

  const toggle = useCallback(() => {
    setOpen(!open);
  }, [open, setOpen]);

  const value = useMemo<NavSidebarContextValue>(
    () => ({ open, hydrated, setOpen, toggle }),
    [open, hydrated, setOpen, toggle]
  );

  return (
    <NavSidebarContext.Provider value={value}>
      {children}
    </NavSidebarContext.Provider>
  );
}

export function useNavSidebar(): NavSidebarContextValue {
  const ctx = useContext(NavSidebarContext);
  if (!ctx) {
    throw new Error(
      "useNavSidebar must be used within a <NavSidebarProvider>. Wrap your authenticated layout with the provider."
    );
  }
  return ctx;
}
