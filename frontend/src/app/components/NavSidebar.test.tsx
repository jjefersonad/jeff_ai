import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

import { NavSidebar } from "./NavSidebar";
import { getVisibleNavEntries, NAV_ENTRIES } from "./navEntries";

const mockUseAuth = vi.fn();
const mockSetOpen = vi.fn();

vi.mock("@/providers/AuthProvider", () => ({
  useAuth: () => mockUseAuth(),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/",
}));

vi.mock("@/app/components/NavSidebarProvider", () => ({
  useNavSidebar: () => ({ open: true, setOpen: mockSetOpen, hydrated: true }),
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

describe("NavSidebar — Esc-to-close parity after shared-hook extraction (crm-lateral-menu-task-hook-1 unit-3 / REQ-004)", () => {
  beforeEach(() => {
    mockUseAuth.mockReset();
    mockUseAuth.mockReturnValue({
      isAuthenticated: true,
      isRehydrating: false,
      user: { username: "alice", role: "user" },
    });
    mockSetOpen.mockClear();
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
  });

  it("WHEN the mobile overlay is open and Escape is pressed THEN setOpen(false) is called", async () => {
    render(<NavSidebar />);
    await screen.findByTestId("nav-sidebar");

    fireEvent.keyDown(window, { key: "Escape" });

    expect(mockSetOpen).toHaveBeenCalledWith(false);
  });
});

describe("NavSidebar — primary nav labels pt-BR (saas-empresario-br-task-ux-2 unit-1 / REQ-003)", () => {
  const ENGLISH_LABELS = ["Chat", "Images", "MCP Servers", "Email"] as const;
  const ENGLISH_DESCRIPTIONS = [
    "Back to the conversation",
    "Browse generated and reference images",
    "Manage Model Context Protocol servers",
    "Token usage by period (admin)",
    "Link your account to other channels (WhatsApp, Telegram)",
    "Manage scheduled tasks",
    "Contacts, companies, and deals",
    "Inbox and connected IMAP/SMTP accounts",
  ] as const;

  const labelByHref = (href: string) =>
    NAV_ENTRIES.find((entry) => entry.href === href)?.label;

  const descriptionByHref = (href: string) =>
    NAV_ENTRIES.find((entry) => entry.href === href)?.description;

  it("WHEN NAV_ENTRIES is inspected THEN no visible item uses an English label", () => {
    for (const entry of NAV_ENTRIES) {
      expect(ENGLISH_LABELS).not.toContain(entry.label);
    }
    for (const entry of getVisibleNavEntries("user")) {
      expect(ENGLISH_LABELS).not.toContain(entry.label);
    }
    for (const entry of getVisibleNavEntries("admin")) {
      expect(ENGLISH_LABELS).not.toContain(entry.label);
    }
  });

  it("WHEN NAV_ENTRIES is inspected THEN English labels map to Conversas, Imagens, Servidores MCP, E-mail", () => {
    expect(labelByHref("/")).toBe("Conversas");
    expect(labelByHref("/images")).toBe("Imagens");
    expect(labelByHref("/mcp-servers")).toBe("Servidores MCP");
    expect(labelByHref("/email")).toBe("E-mail");
  });

  it("WHEN NAV_ENTRIES is inspected THEN Integrações, Agendamentos, CRM, Consumo, Usuários remain in Portuguese", () => {
    expect(labelByHref("/integrations")).toBe("Integrações");
    expect(labelByHref("/scheduling")).toBe("Agendamentos");
    expect(labelByHref("/crm")).toBe("CRM");
    expect(labelByHref("/usage")).toBe("Consumo");
    expect(labelByHref("/admin/users")).toBe("Usuários");
  });

  it("WHEN NAV_ENTRIES is inspected THEN Perfis de agente points at /agent-profiles (ui-1 / REQ-001)", () => {
    expect(labelByHref("/agent-profiles")).toBe("Perfis de agente");
    expect(
      getVisibleNavEntries("user").some((entry) => entry.href === "/agent-profiles")
    ).toBe(true);
  });

  it("WHEN NAV_ENTRIES is inspected THEN descriptions that were English are pt-BR equivalents", () => {
    for (const entry of NAV_ENTRIES) {
      expect(ENGLISH_DESCRIPTIONS).not.toContain(entry.description);
    }
    expect(descriptionByHref("/")).toBe("Voltar para a conversa");
    expect(descriptionByHref("/images")).toBe(
      "Ver imagens geradas e de referência"
    );
    expect(descriptionByHref("/mcp-servers")).toBe(
      "Gerenciar servidores Model Context Protocol"
    );
    expect(descriptionByHref("/email")).toBe(
      "Caixa de entrada e contas IMAP/SMTP conectadas"
    );
    expect(descriptionByHref("/usage")).toBe("Uso de tokens por período (admin)");
    expect(descriptionByHref("/integrations")).toBe(
      "Vincule sua conta a outros canais (WhatsApp, Telegram)"
    );
    expect(descriptionByHref("/scheduling")).toBe("Gerenciar tarefas agendadas");
    expect(descriptionByHref("/crm")).toBe("Contatos, empresas e negócios");
    expect(descriptionByHref("/admin/users")).toBe("Gerenciar usuários (admin)");
  });
});

describe("NavSidebar — sidebar header and MCP for role=user (saas-empresario-br-task-ux-2 unit-2 / REQ-003)", () => {
  beforeEach(() => {
    mockUseAuth.mockReset();
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
    mockUseAuth.mockReturnValue({
      isAuthenticated: true,
      isRehydrating: false,
      user: { username: "alice", role: "user" },
    });
  });

  it("WHEN role=user THEN the sidebar header is Menu and not Navigation", () => {
    render(<NavSidebar />);

    expect(screen.getByText("Menu")).toBeInTheDocument();
    expect(screen.queryByText("Navigation")).not.toBeInTheDocument();
  });

  it("WHEN role=user THEN Servidores MCP remains listed (renamed, not hidden)", () => {
    render(<NavSidebar />);

    const mcp = screen.getByRole("link", { name: /servidores mcp/i });
    expect(mcp).toBeInTheDocument();
    expect(mcp).toHaveAttribute("href", "/mcp-servers");
    expect(
      getVisibleNavEntries("user").some((entry) => entry.href === "/mcp-servers")
    ).toBe(true);
  });

  it("WHEN role=user THEN Perfis de agente is listed at /agent-profiles (ui-1 / REQ-001)", () => {
    render(<NavSidebar />);

    const profiles = screen.getByRole("link", { name: /perfis de agente/i });
    expect(profiles).toBeInTheDocument();
    expect(profiles).toHaveAttribute("href", "/agent-profiles");
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
