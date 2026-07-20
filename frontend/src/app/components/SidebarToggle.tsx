"use client";

/**
 * Hamburger button in the top bar that toggles the navigation sidebar.
 *
 * Sits in the top bar at the far left, next to the project name. Its
 * `aria-expanded` reflects the provider's open state so screen readers
 * announce the toggle correctly. Click, `Enter`, and `Space` all toggle
 * (the underlying `Button` is a real `<button>`).
 *
 * Persistence and behaviour live in `<NavSidebarProvider />` — this
 * component is presentational.
 */

import { Menu } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useNavSidebar } from "@/app/components/NavSidebarProvider";

export function SidebarToggle() {
  const { open, toggle } = useNavSidebar();

  return (
    <Button
      type="button"
      variant="ghost"
      size="icon"
      onClick={toggle}
      aria-label="Toggle navigation"
      aria-expanded={open}
      aria-controls="jeff-ai-primary-nav"
      title="Toggle navigation"
    >
      <Menu aria-hidden="true" />
    </Button>
  );
}
