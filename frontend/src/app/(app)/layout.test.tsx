import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";

import AppLayout from "./layout";

vi.mock("@/app/components/SidebarToggle", () => ({
  SidebarToggle: () => <button aria-label="Toggle sidebar" />,
}));

vi.mock("@/app/components/UserMenu", () => ({
  UserMenu: () => <div data-testid="user-menu" />,
}));

vi.mock("@/app/components/NavSidebar", () => ({
  NavSidebar: () => <nav data-testid="nav-sidebar" />,
}));

vi.mock("@/app/components/NavSidebarProvider", () => ({
  NavSidebarProvider: ({ children }: { children: ReactNode }) => (
    <>{children}</>
  ),
}));

describe("AppLayout — chat-viewport-docking REQ-004 (task-verify-1)", () => {
  it("retains the shared h-screen root and overflow-y-auto children region unchanged, so /images, /mcp-servers, /usage keep their scroll behavior", () => {
    const { container } = render(
      <AppLayout>
        <div data-testid="page-content">content</div>
      </AppLayout>
    );

    const root = container.firstElementChild as HTMLElement;
    expect(root.className).toMatch(/\bh-screen\b/);

    const childrenRegion = screen.getByTestId("page-content")
      .parentElement as HTMLElement;
    expect(childrenRegion.className).toMatch(/\bflex-1\b/);
    expect(childrenRegion.className).toMatch(/\boverflow-y-auto\b/);
  });
});
