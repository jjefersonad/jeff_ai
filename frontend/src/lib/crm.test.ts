import { describe, expect, it } from "vitest";

import { validateContactForm } from "./crm";

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
