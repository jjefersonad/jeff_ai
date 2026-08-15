import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";

import { EnvelopeApprovalInterrupt } from "./EnvelopeApprovalInterrupt";
import type { EnvelopeProposalInterruptData } from "@/app/types/types";

const envelope: EnvelopeProposalInterruptData = {
  type: "envelope_proposal",
  proposal: {
    required_capabilities: [
      { capability: "write_existing", justification: "editar um arquivo" },
    ],
    excluded_capabilities: ["shell"],
  },
};

describe("EnvelopeApprovalInterrupt — saas-empresario-br-task-ux-3 unit-4 / REQ-004", () => {
  it("shows Aprovar and Recusar instead of Grant / Deny as primary copy", () => {
    render(
      <EnvelopeApprovalInterrupt
        envelope={envelope}
        onResume={vi.fn()}
      />
    );

    expect(screen.getByRole("button", { name: /aprovar/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /recusar/i })).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /^grant$/i })
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /^deny$/i })
    ).not.toBeInTheDocument();
    expect(screen.queryByText("Approve")).not.toBeInTheDocument();
    expect(screen.queryByText("Reject")).not.toBeInTheDocument();
    expect(screen.queryByText("Save & Approve")).not.toBeInTheDocument();
  });
});
