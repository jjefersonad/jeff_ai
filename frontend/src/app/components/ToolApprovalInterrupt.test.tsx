import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { readFileSync } from "node:fs";
import path from "node:path";

import { ToolApprovalInterrupt } from "./ToolApprovalInterrupt";

describe("ToolApprovalInterrupt — saas-empresario-br-task-ux-3 unit-4 / REQ-004", () => {
  it("shows Aprovar and Recusar instead of Approve / Reject", () => {
    render(
      <ToolApprovalInterrupt
        actionRequest={{ name: "edit_file", args: { path: "foo.ts" } }}
        onResume={vi.fn()}
      />
    );

    expect(screen.getByRole("button", { name: /aprovar/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /recusar/i })).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /^approve$/i })
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /^reject$/i })
    ).not.toBeInTheDocument();
  });

  it("shows Salvar e aprovar instead of Save & Approve when editing args", async () => {
    const user = userEvent.setup();
    render(
      <ToolApprovalInterrupt
        actionRequest={{ name: "edit_file", args: { path: "foo.ts" } }}
        onResume={vi.fn()}
      />
    );

    await user.click(screen.getByRole("button", { name: /edit/i }));

    expect(
      screen.getByRole("button", { name: /salvar e aprovar/i })
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /save & approve/i })
    ).not.toBeInTheDocument();
  });

  it("does not change interrupt_on or tier protocol — copy only", () => {
    const source = readFileSync(
      path.resolve(__dirname, "./ToolApprovalInterrupt.tsx"),
      "utf8"
    );
    expect(source).not.toMatch(/from ["']@\/.*tier_config/);
    expect(source).toMatch(/type: "approve"/);
    expect(source).toMatch(/type: "reject"/);
  });
});
