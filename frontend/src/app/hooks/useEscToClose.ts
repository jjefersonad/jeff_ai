"use client";

import { useEffect } from "react";

/**
 * Calls `onClose` when `Escape` is pressed, while `enabled` is true.
 * Extracted from `NavSidebar.tsx`'s local implementation once a third
 * consumer (the CRM lateral menu) needed the same effect — see design
 * decision D3 of `crm-lateral-menu-design`.
 */
export function useEscToClose(enabled: boolean, onClose: () => void) {
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
