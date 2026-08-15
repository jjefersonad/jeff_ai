import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";

import { setUnauthorizedHandler } from "./api";
import {
  listContacts,
  resolveNotesTarget,
  validateContactForm,
} from "./crm";

describe("validateContactForm (add-simple-crm-module-task-frontend-2 unit-1 / REQ-001)", () => {
  it("WHEN name without email and phone THEN invalid and blocks submit", () => {
    const result = validateContactForm({ name: "Ana", email: "", phone: "" });
    expect(result.valid).toBe(false);
    expect(result.error).toMatch(/e-mail|telefone/i);
  });

  it("WHEN name with email THEN valid", () => {
    expect(
      validateContactForm({ name: "Ana", email: "ana@example.com", phone: "" })
        .valid
    ).toBe(true);
  });
});

describe("listContacts paginated envelope (crm-ext-task-frontend-1 unit-1 / REQ-ADD-003)", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    process.env.NEXT_PUBLIC_API_URL = "http://backend.test";
  });

  afterEach(() => {
    global.fetch = originalFetch;
    setUnauthorizedHandler(null);
  });

  it("WHEN API returns {items,total,page,page_size} THEN listContacts returns the envelope", async () => {
    const envelope = {
      items: [
        {
          id: "c1",
          user_id: "u1",
          name: "Ana",
          email: "a@x.com",
          phone: null,
          company_id: null,
          status: null,
          tags: [],
          city: "SP",
          state: "SP",
          custom_values: {},
          archived_at: null,
          created_at: "2026-08-01T00:00:00Z",
          updated_at: "2026-08-01T00:00:00Z",
        },
      ],
      total: 1,
      page: 1,
      page_size: 20,
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify(envelope), { status: 200 }));
    global.fetch = fetchMock;

    const result = await listContacts({ page: 1, page_size: 20 });

    expect(result).toEqual(envelope);
    expect(Array.isArray(result)).toBe(false);
    expect(result.items).toHaveLength(1);
    expect(result.total).toBe(1);
    const [url] = fetchMock.mock.calls[0];
    expect(String(url)).toContain("/api/crm/contacts");
    expect(String(url)).toContain("page=1");
    expect(String(url)).toContain("page_size=20");
  });

  it("WHEN API returns a bare array THEN listContacts normalizes to an envelope", async () => {
    const rows = [
      {
        id: "c1",
        user_id: "u1",
        name: "Ana",
        email: "a@x.com",
        phone: null,
        company_id: null,
        status: null,
        tags: [],
        city: null,
        state: null,
        custom_values: {},
        archived_at: null,
        created_at: "2026-08-01T00:00:00Z",
        updated_at: "2026-08-01T00:00:00Z",
      },
    ];
    global.fetch = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify(rows), { status: 200 }));

    const result = await listContacts();

    expect(result.items).toEqual(rows);
    expect(result.total).toBe(1);
    expect(result.page).toBe(1);
  });
});

describe("resolveNotesTarget — associations by tab", () => {
  const allSelected = {
    contactId: "c1",
    companyId: "co1",
    dealId: "d1",
  };

  it("contacts tab uses only contact_id even if company/deal are also selected", () => {
    expect(resolveNotesTarget({ tab: "contacts", ...allSelected })).toEqual({
      contact_id: "c1",
    });
  });

  it("companies tab uses only company_id", () => {
    expect(resolveNotesTarget({ tab: "companies", ...allSelected })).toEqual({
      company_id: "co1",
    });
  });

  it("pipeline tab uses only deal_id (never contact notes on a lead)", () => {
    expect(resolveNotesTarget({ tab: "pipeline", ...allSelected })).toEqual({
      deal_id: "d1",
    });
  });

  it("pipeline with no deal selected returns null even if contact is selected", () => {
    expect(
      resolveNotesTarget({
        tab: "pipeline",
        contactId: "c1",
        companyId: null,
        dealId: null,
      })
    ).toBeNull();
  });

  it("contacts with no contact selected returns null", () => {
    expect(
      resolveNotesTarget({
        tab: "contacts",
        contactId: null,
        companyId: "co1",
        dealId: "d1",
      })
    ).toBeNull();
  });
});

describe("contacts list helpers (crm-ext-task-frontend-2 unit-1 / REQ-ADD-005)", () => {
  it("formats updated_at for display and keeps resolveNotesTarget stable", async () => {
    const { formatCrmTimestamp, contactsListUsesTableLayout, CONTACT_LIST_COLUMNS } =
      await import("./crm");
    expect(CONTACT_LIST_COLUMNS).toEqual([
      "name",
      "email",
      "phone",
      "updated_at",
    ]);
    expect(formatCrmTimestamp("2026-08-01T15:30:00.000Z")).toMatch(/\d/);
    expect(formatCrmTimestamp("not-a-date")).toBe("");
    expect(contactsListUsesTableLayout(767)).toBe(false);
    expect(contactsListUsesTableLayout(768)).toBe(true);
    expect(
      resolveNotesTarget({
        tab: "contacts",
        contactId: "c1",
        companyId: null,
        dealId: null,
      })
    ).toEqual({ contact_id: "c1" });
  });
});

describe("buildContactWritePayload (crm-ext-task-frontend-3 unit-1 / REQ-ADD-001)", () => {
  it("includes city/state/custom_values and omits editable timestamps", async () => {
    const { buildContactWritePayload } = await import("./crm");
    const payload = buildContactWritePayload({
      name: " Ana ",
      email: "ana@x.com",
      phone: "",
      city: "Curitiba",
      state: "PR",
      custom_values: { segmento: "PME" },
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-02T00:00:00Z",
    });
    expect(payload).toEqual({
      name: "Ana",
      email: "ana@x.com",
      phone: null,
      company_id: null,
      city: "Curitiba",
      state: "PR",
      whatsapp_opt_in: false,
      custom_values: { segmento: "PME" },
    });
    expect(payload).not.toHaveProperty("created_at");
    expect(payload).not.toHaveProperty("updated_at");
  });

  it("includes whatsapp_opt_in in the write payload (saas-empresario-br-task-crm-ui-1 unit-2)", async () => {
    const { buildContactWritePayload } = await import("./crm");
    const optedIn = buildContactWritePayload({
      name: "Ana",
      email: "ana@x.com",
      whatsapp_opt_in: true,
    });
    expect(optedIn.whatsapp_opt_in).toBe(true);

    const optedOut = buildContactWritePayload({
      name: "Ana",
      email: "ana@x.com",
      whatsapp_opt_in: false,
    });
    expect(optedOut.whatsapp_opt_in).toBe(false);
  });
});

describe("DEAL_STAGE_LABELS (saas-empresario-br-task-crm-ui-2 unit-1 / REQ-007)", () => {
  it("maps canonical Deal.stage values to pt-BR labels without changing persisted keys", async () => {
    const { DEAL_STAGE_LABELS, dealStageLabel } = await import("./crm");
    expect(DEAL_STAGE_LABELS).toEqual({
      lead: "Lead",
      qualified: "Qualificado",
      proposal: "Proposta",
      negotiation: "Negociação",
      won: "Ganho",
      lost: "Perdido",
    });
    expect(dealStageLabel("lead")).toBe("Lead");
    expect(dealStageLabel("qualified")).toBe("Qualificado");
    expect(dealStageLabel("proposal")).toBe("Proposta");
    expect(dealStageLabel("negotiation")).toBe("Negociação");
    expect(dealStageLabel("won")).toBe("Ganho");
    expect(dealStageLabel("lost")).toBe("Perdido");
    expect(dealStageLabel("unknown-stage")).toBe("unknown-stage");
  });
});

function visibleCurrency(value: string | null): string | null {
  return value?.replace(/\u00a0/g, " ") ?? null;
}

describe("formatDealValue (saas-empresario-br-task-crm-ui-2 unit-2 / REQ-007)", () => {
  it("formats 1500 as R$ 1.500,00 not BRL 1500", async () => {
    const { formatDealValue } = await import("./crm");
    expect(visibleCurrency(formatDealValue(1500))).toBe("R$ 1.500,00");
    expect(visibleCurrency(formatDealValue(1500, "BRL"))).toBe("R$ 1.500,00");
    expect(visibleCurrency(formatDealValue(1500, null))).toBe("R$ 1.500,00");
    expect(visibleCurrency(formatDealValue("1500"))).toBe("R$ 1.500,00");
    expect(formatDealValue(1500)).not.toMatch(/BRL/);
  });

  it("returns null for missing values so the UI does not show BRL or undefined", async () => {
    const { formatDealValue } = await import("./crm");
    expect(formatDealValue(null)).toBeNull();
    expect(formatDealValue(undefined)).toBeNull();
    expect(formatDealValue("")).toBeNull();
    expect(formatDealValue(Number.NaN)).toBeNull();
  });
});

describe("slugifyFieldKey", () => {
  it("normalizes labels to valid CRM field keys", async () => {
    const { slugifyFieldKey } = await import("./crm");
    expect(slugifyFieldKey("Segmento")).toBe("segmento");
    expect(slugifyFieldKey("Ticket Médio")).toBe("ticket_medio");
    expect(slugifyFieldKey("123abc")).toBe("f_123abc");
  });
});
