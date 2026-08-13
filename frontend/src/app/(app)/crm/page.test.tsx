/**
 * CRM page tabs after correct-funil-lead-as-deal (frontend-funil-1)
 * and Novo Lead form payload.
 *
 * unit-1: Contatos, Empresas, Funil — no Leads tab / LeadsPanel.
 * REQ-002: Funil submit with email sends nested `contact` and refreshes.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import CrmPage from "./page";
import { createDeal, createNote, listContacts, listDeals } from "@/lib/crm";

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

describe("CRM page tabs (correct-funil-lead-as-deal-task-frontend-funil-1)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("unit-1: tab list is Contatos, Empresas, Funil with no Leads tab", async () => {
    render(<CrmPage />);

    await waitFor(() => {
      expect(screen.getByRole("tab", { name: "Contatos" })).toBeInTheDocument();
    });
    expect(screen.getByRole("tab", { name: "Empresas" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Funil" })).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: /leads/i })).not.toBeInTheDocument();
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
      expect(screen.getByRole("tab", { name: "Funil" })).toBeInTheDocument();
    });
    await user.click(screen.getByRole("tab", { name: "Funil" }));
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
