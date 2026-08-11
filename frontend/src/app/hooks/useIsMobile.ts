"use client";

import { useEffect, useState } from "react";

export const MOBILE_BREAKPOINT = 768; // px — see design D3 of mobile-conversations-drawer.

/**
 * SSR-safe: starts `false` (desktop) on both server and client, then syncs
 * to the real value in the effect. This avoids hydration mismatch and keeps
 * the desktop default behaviour during the first paint.
 */
export function useIsMobile(): boolean {
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
