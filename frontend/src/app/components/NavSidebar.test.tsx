import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";

import { NavSidebar } from "./NavSidebar";
import { getVisibleNavEntries, NAV_ENTRIES } from "./navEntries";

const mockUseAuth = vi.fn();

vi.mock("@/providers/AuthProvider", () => ({
  useAuth: () => mockUseAuth(),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/",
}));

vi.mock("@/app/components/NavSidebarProvider", () => ({
  useNavSidebar: () => ({ open: true, setOpen: vi.fn(), hydrated: true }),
}));

describe("NavSidebar — usage entry gated by admin role (reporting-2 unit-1 / REQ-006)", () => {
  beforeEach(() => {
    mockUseAuth.mockReset();
    // Desktop layout (inline panel) — matchMedia returns false for mobile.
    Object.defineProperty(window, "matchMedia", {
      writable: true,
      value: vi.fn().mockImplementation((query: string) => ({
        matches: false,
        media: query,
        onchange: null,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    });
  });

  it("WHEN role=user THEN the usage nav entry does not appear", () => {
    mockUseAuth.mockReturnValue({
      isAuthenticated: true,
      isRehydrating: false,
      user: { username: "alice", role: "user" },
    });

    render(<NavSidebar />);

    expect(
      screen.queryByRole("link", { name: /consumo/i })
    ).not.toBeInTheDocument();
  });

  it("WHEN role=admin THEN the usage nav entry appears", () => {
    mockUseAuth.mockReturnValue({
      isAuthenticated: true,
      isRehydrating: false,
      user: { username: "admin", role: "admin" },
    });

    render(<NavSidebar />);

    expect(
      screen.getByRole("link", { name: /consumo/i })
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /consumo/i })).toHaveAttribute(
      "href",
      "/usage"
    );
  });
});

describe("NavSidebar — Usuários entry gated by admin role (user-management-frontend-5 unit-1 / REQ-005)", () => {
  beforeEach(() => {
    mockUseAuth.mockReset();
    // Desktop layout (inline panel) — matchMedia returns false for mobile.
    Object.defineProperty(window, "matchMedia", {
      writable: true,
      value: vi.fn().mockImplementation((query: string) => ({
        matches: false,
        media: query,
        onchange: null,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    });
  });

  it("unit-1: WHEN role=admin THEN the Usuários nav entry appears with href=/admin/users", () => {
    mockUseAuth.mockReturnValue({
      isAuthenticated: true,
      isRehydrating: false,
      user: { username: "admin", role: "admin" },
    });

    render(<NavSidebar />);

    // The "Usuários" link MUST be in the document and point to /admin/users
    // — REQ-005 scenario "Admin vê o item de menu". The link's accessible
    // name matches the entry label; we use a scoped regex so we don't
    // false-match a future "Gerenciar usuários" entry.
    const link = screen.getByRole("link", { name: /usuários/i });
    expect(link).toBeInTheDocument();
    expect(link).toHaveAttribute("href", "/admin/users");
  });
});

describe("NavSidebar — CRM entry (add-simple-crm-module-task-frontend-1 unit-1 / REQ-ADD-001)", () => {
  it("WHEN ENTRIES is inspected THEN CRM href=/crm exists without requireRole admin", () => {
    const crm = NAV_ENTRIES.find((entry) => entry.href === "/crm");
    expect(crm).toBeDefined();
    expect(crm?.requireRole).toBeUndefined();
    expect(getVisibleNavEntries("user").some((e) => e.href === "/crm")).toBe(
      true
    );
  });
});

describe("NavSidebar — responsive rendering unaffected by hook extraction (mobile-conversations-drawer-task-hook-1 unit-2 / REQ-001)", () => {
  beforeEach(() => {
    mockUseAuth.mockReturnValue({
      isAuthenticated: true,
      isRehydrating: false,
      user: { username: "alice", role: "user" },
    });
  });

  it("WHEN viewport is mobile-width THEN the nav renders as a fixed overlay drawer with a close button", async () => {
    Object.defineProperty(window, "matchMedia", {
      writable: true,
      value: vi.fn().mockImplementation((query: string) => ({
        matches: true,
        media: query,
        onchange: null,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    });

    render(<NavSidebar />);

    const nav = await screen.findByTestId("nav-sidebar");
    expect(nav.className).toContain("fixed");
    expect(
      screen.getByRole("button", { name: /close navigation/i })
    ).toBeInTheDocument();
  });

  it("WHEN viewport is desktop-width THEN the nav renders as an inline push panel with no close button", async () => {
    Object.defineProperty(window, "matchMedia", {
      writable: true,
      value: vi.fn().mockImplementation((query: string) => ({
        matches: false,
        media: query,
        onchange: null,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    });

    render(<NavSidebar />);

    const nav = await screen.findByTestId("nav-sidebar");
    expect(nav.className).not.toContain("fixed");
    expect(
      screen.queryByRole("button", { name: /close navigation/i })
    ).not.toBeInTheDocument();
  });
});

describe("NavSidebar — Usuários entry hidden for non-admin (user-management-frontend-5 unit-2 / REQ-005)", () => {
  beforeEach(() => {
    mockUseAuth.mockReset();
    // Desktop layout (inline panel) — matchMedia returns false for mobile.
    Object.defineProperty(window, "matchMedia", {
      writable: true,
      value: vi.fn().mockImplementation((query: string) => ({
        matches: false,
        media: query,
        onchange: null,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    });
  });

  it("unit-2: WHEN role=user THEN the Usuários nav entry does NOT appear", () => {
    mockUseAuth.mockReturnValue({
      isAuthenticated: true,
      isRehydrating: false,
      user: { username: "alice", role: "user" },
    });

    render(<NavSidebar />);

    // REQ-005 scenario "Usuário comum não vê o item de menu": the link
    // MUST be absent from the DOM (not merely hidden / aria-hidden).
    expect(
      screen.queryByRole("link", { name: /usuários/i })
    ).not.toBeInTheDocument();
  });
});
