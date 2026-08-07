import { describe, expect, it } from "vitest";

import { resolveNotesTarget, validateContactForm } from "./crm";

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
