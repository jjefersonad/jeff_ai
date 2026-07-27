import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";

import { NavSidebar } from "./NavSidebar";

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
