/**
 * CRM page — lateral menu (crm-lateral-menu) replaces the old Tabs-based
 * navigation. Sections (Contatos, Empresas, Funil) are switched via
 * CrmSidebarMenu instead of shadcn Tabs/TabsTrigger.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";

import CrmPage from "./page";
import { createDeal, createNote, listContacts, listDeals } from "@/lib/crm";

let mockCrmMenu: string | null = null;
const mockSetCrmMenu = vi.fn((v: string | null) => {
  mockCrmMenu = v;
});

vi.mock("nuqs", () => ({
  useQueryState: (key: string) => {
    if (key === "crmMenu") return [mockCrmMenu, mockSetCrmMenu];
    return [null, vi.fn()];
  },
}));

let mockIsMobile = false;
vi.mock("@/app/hooks/useIsMobile", () => ({
  useIsMobile: () => mockIsMobile,
}));

vi.mock("@/components/ui/resizable", () => ({
  ResizablePanelGroup: ({ children }: { children: ReactNode }) => (
    <div data-testid="resizable-panel-group">{children}</div>
  ),
  ResizablePanel: ({
    children,
    id,
  }: {
    children: ReactNode;
    id?: string;
  }) => <div data-testid={`resizable-panel-${id}`}>{children}</div>,
  ResizableHandle: () => <div data-testid="resizable-handle" />,
}));

vi.mock("@/lib/crm", async () => {
  const actual = await vi.importActual<typeof import("@/lib/crm")>("@/lib/crm");
  return {
    ...actual,
    listContacts: vi.fn(async () => ({ items: [], total: 0 })),
    listCompanies: vi.fn(async () => []),
    listDeals: vi.fn(async () => []),
    listDealStages: vi.fn(async () => [
      "lead",
      "qualified",
      "proposal",
      "negotiation",
      "won",
      "lost",
    ]),
    listFieldDefinitions: vi.fn(async () => []),
    listNotes: vi.fn(async () => []),
    createDeal: vi.fn(),
    createNote: vi.fn(),
    updateDeal: vi.fn(),
  };
});

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

describe("CRM page — section content via lateral menu (correct-funil-lead-as-deal-task-frontend-funil-1)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockCrmMenu = "1";
    mockIsMobile = false;
  });

  it("unit-1: lateral menu lists Contatos, Empresas, Funil with no Leads entry", async () => {
    render(<CrmPage />);

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: "Contatos" })
      ).toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: "Empresas" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Funil" })).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /leads/i })
    ).not.toBeInTheDocument();
    expect(screen.queryByText("LeadsPanel")).not.toBeInTheDocument();
  });

  it("REQ-002: Funil submit with email sends nested contact and refreshes contacts", async () => {
    const user = userEvent.setup();
    vi.mocked(createDeal).mockResolvedValue({
      id: "deal-new",
      user_id: "user-1",
      title: "Lead Acme",
      stage: "lead",
      value: null,
      currency: null,
      contact_id: "contact-new",
      company_id: null,
      custom_values: {},
      archived_at: null,
      created_at: "2026-08-12T00:00:00Z",
      updated_at: "2026-08-12T00:00:00Z",
    });

    render(<CrmPage />);
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Funil" })).toBeInTheDocument();
    });
    await user.click(screen.getByRole("button", { name: "Funil" }));
    await user.click(screen.getByRole("button", { name: /^adicionar$/i }));
    await user.type(screen.getByLabelText(/^nome/i), "Lead Acme");
    await user.type(screen.getByLabelText(/^e-mail$/i), "ana@x.com");
    await user.type(
      screen.getByLabelText(/^descrição$/i),
      "Primeira conversa"
    );
    await user.click(screen.getByRole("button", { name: /^criar$/i }));

    await waitFor(() => {
      expect(createDeal).toHaveBeenCalledWith(
        expect.objectContaining({
          title: "Lead Acme",
          stage: "lead",
          contact: expect.objectContaining({
            name: "Lead Acme",
            email: "ana@x.com",
          }),
        })
      );
    });
    expect(createNote).toHaveBeenCalledWith(
      expect.objectContaining({
        deal_id: "deal-new",
        body: "Primeira conversa",
        source: "user",
      })
    );
    expect(vi.mocked(listContacts).mock.calls.length).toBeGreaterThan(1);
    expect(vi.mocked(listDeals).mock.calls.length).toBeGreaterThan(1);
  });
});

describe("CRM page — lateral menu trigger (crm-lateral-menu-task-page-1)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockCrmMenu = null;
    mockIsMobile = false;
  });

  it("unit-1: WHEN crmMenu is unset and the trigger is clicked THEN crmMenu opens", async () => {
    const user = userEvent.setup();
    render(<CrmPage />);

    await user.click(screen.getByRole("button", { name: /menu/i }));

    expect(mockSetCrmMenu).toHaveBeenCalledWith("1");
  });

  it("unit-2: WHEN crmMenu is set and the trigger is clicked THEN crmMenu closes", async () => {
    mockCrmMenu = "1";
    const user = userEvent.setup();
    render(<CrmPage />);

    await user.click(screen.getByRole("button", { name: /menu/i }));

    expect(mockSetCrmMenu).toHaveBeenCalledWith(null);
  });

  it("unit-3: WHEN rendered THEN the trigger button is present regardless of crmMenu", async () => {
    render(<CrmPage />);
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /menu/i })
      ).toBeInTheDocument();
    });

    mockCrmMenu = "1";
    render(<CrmPage />);
    expect(
      screen.getAllByRole("button", { name: /menu/i })[0]
    ).toBeInTheDocument();
  });
});

describe("CRM page — lateral menu responsive rendering (crm-lateral-menu-task-page-2 / REQ-003)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockCrmMenu = "1";
  });

  it("unit-1: on mobile, renders a fixed backdrop + w-72 drawer wrapping CrmSidebarMenu, with no ResizablePanel for crm-menu", async () => {
    mockIsMobile = true;

    render(<CrmPage />);

    const backdrop = await screen.findByTestId("crm-menu-backdrop");
    expect(backdrop.className).toContain("fixed");
    expect(backdrop.className).toContain("inset-0");
    expect(backdrop.className).toContain("bg-black/50");

    const drawer = screen.getByTestId("crm-menu-drawer");
    expect(drawer.className).toContain("fixed");
    expect(drawer.className).toContain("inset-y-0");
    expect(drawer.className).toContain("left-0");
    expect(drawer.className).toContain("w-72");

    expect(
      screen.queryByTestId("resizable-panel-crm-menu")
    ).not.toBeInTheDocument();
    expect(screen.queryByTestId("resizable-handle")).not.toBeInTheDocument();
  });

  it("unit-2: on desktop, renders ResizablePanel/ResizableHandle for crm-menu with no backdrop or fixed drawer", async () => {
    mockIsMobile = false;

    render(<CrmPage />);

    await waitFor(() => {
      expect(
        screen.getByTestId("resizable-panel-crm-menu")
      ).toBeInTheDocument();
    });
    expect(screen.getByTestId("resizable-handle")).toBeInTheDocument();
    expect(screen.getByTestId("resizable-panel-crm-content")).toBeInTheDocument();

    expect(screen.queryByTestId("crm-menu-backdrop")).not.toBeInTheDocument();
    expect(screen.queryByTestId("crm-menu-drawer")).not.toBeInTheDocument();
  });

  it("unit-3: on mobile, clicking the backdrop closes the menu (crmMenu cleared)", async () => {
    mockIsMobile = true;
    const user = userEvent.setup();

    render(<CrmPage />);

    await user.click(await screen.findByTestId("crm-menu-backdrop"));

    expect(mockSetCrmMenu).toHaveBeenCalledWith(null);
  });

  it("unit-4: TabsList/TabsTrigger no longer render anywhere on /crm", async () => {
    mockIsMobile = false;

    render(<CrmPage />);

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: "Contatos" })
      ).toBeInTheDocument();
    });
    expect(screen.queryAllByRole("tab")).toHaveLength(0);
  });
});

describe("CRM page — selecting a section switches the active panel (crm-lateral-menu-task-page-2 / REQ-002)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockCrmMenu = "1";
    mockIsMobile = false;
  });

  it("unit-1: selecting Contatos renders ContactsPanel", async () => {
    const user = userEvent.setup();
    render(<CrmPage />);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Contatos" })).toBeInTheDocument();
    });
    await user.click(screen.getByRole("button", { name: "Contatos" }));

    expect(
      screen.getByRole("button", { name: "Contatos" })
    ).toHaveAttribute("aria-current", "true");
  });

  it("unit-2: selecting Empresas renders CompaniesPanel", async () => {
    const user = userEvent.setup();
    render(<CrmPage />);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Empresas" })).toBeInTheDocument();
    });
    await user.click(screen.getByRole("button", { name: "Empresas" }));

    expect(
      screen.getByRole("button", { name: "Empresas" })
    ).toHaveAttribute("aria-current", "true");
  });

  it("unit-3: selecting Funil renders FunilPanel", async () => {
    const user = userEvent.setup();
    render(<CrmPage />);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Funil" })).toBeInTheDocument();
    });
    await user.click(screen.getByRole("button", { name: "Funil" }));

    expect(screen.getByRole("button", { name: "Funil" })).toHaveAttribute(
      "aria-current",
      "true"
    );
    expect(screen.getByRole("button", { name: /^adicionar$/i })).toBeInTheDocument();
  });
});

describe("CRM page — mobile selection closes the overlay (crm-lateral-menu-task-page-3 / REQ-003)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockCrmMenu = "1";
    mockIsMobile = true;
  });

  it("unit-4: WHEN an entry is selected on mobile THEN crmMenu is cleared in addition to switching the panel", async () => {
    const user = userEvent.setup();
    render(<CrmPage />);

    await user.click(await screen.findByRole("button", { name: "Empresas" }));

    expect(mockSetCrmMenu).toHaveBeenCalledWith(null);
  });
});

describe("CRM page — lateral menu accessibility (crm-lateral-menu-task-page-4 / REQ-004)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockIsMobile = false;
  });

  it("unit-1: trigger button has aria-label and aria-expanded reflecting crmMenu", async () => {
    mockCrmMenu = null;
    render(<CrmPage />);

    const trigger = await screen.findByRole("button", { name: /menu/i });
    expect(trigger).toHaveAttribute("aria-label");
    expect(trigger).toHaveAttribute("aria-expanded", "false");
  });

  it("unit-1: aria-expanded is true when crmMenu is set", async () => {
    mockCrmMenu = "1";
    render(<CrmPage />);

    const trigger = await screen.findByRole("button", { name: /menu/i });
    expect(trigger).toHaveAttribute("aria-expanded", "true");
  });

  it("unit-2: the CRM menu is exposed as a navigation landmark", async () => {
    mockCrmMenu = "1";
    render(<CrmPage />);

    expect(await screen.findByRole("navigation")).toBeInTheDocument();
  });

  it("unit-3: WHEN the mobile overlay is open and Escape is pressed THEN it closes and focus returns to the trigger", async () => {
    mockCrmMenu = "1";
    mockIsMobile = true;
    render(<CrmPage />);

    await screen.findByTestId("crm-menu-drawer");
    fireEvent.keyDown(window, { key: "Escape" });

    expect(mockSetCrmMenu).toHaveBeenCalledWith(null);
    expect(screen.getByRole("button", { name: /menu/i })).toHaveFocus();
  });
});
