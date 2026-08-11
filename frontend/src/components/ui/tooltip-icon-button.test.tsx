import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";

import { Mail } from "lucide-react";

import { TooltipIconButton } from "./tooltip-icon-button";

describe("TooltipIconButton — aria-label (email-inbox-ux-improvements task-shared-1 / REQ-010)", () => {
  it("unit-1: WHEN ariaLabel is passed explicitly THEN it wins over the tooltip text", () => {
    render(
      <TooltipIconButton
        icon={<Mail />}
        onClick={vi.fn()}
        tooltip="Excluir"
        ariaLabel="Excluir e-mail"
      />
    );

    expect(screen.getByRole("button", { name: "Excluir e-mail" })).toBeInTheDocument();
  });

  it("unit-2: WHEN ariaLabel is omitted THEN it falls back to the tooltip text", () => {
    render(<TooltipIconButton icon={<Mail />} onClick={vi.fn()} tooltip="Responder" />);

    expect(screen.getByRole("button", { name: "Responder" })).toBeInTheDocument();
  });
});
