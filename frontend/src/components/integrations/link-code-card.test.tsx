import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { LinkCodeCard } from "./link-code-card";

vi.mock("sonner", () => ({
  toast: { success: vi.fn() },
}));

describe("LinkCodeCard (telegram-integration-frontend-registration-task-component-1 unit-1/2 / design-D2)", () => {
  const writeText = vi.fn().mockResolvedValue(undefined);

  beforeEach(() => {
    writeText.mockClear();
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText },
      configurable: true,
    });
  });

  it("WHEN rendered THEN shows the code in mono, a localized expiry, and a copy button", () => {
    const expiresAt = "2026-08-09T12:00:00Z";
    render(<LinkCodeCard code="ABC123" expiresAt={expiresAt} />);

    const codeEl = screen.getByText("ABC123");
    expect(codeEl.className).toContain("font-mono");
    expect(
      screen.getByText(new RegExp(new Date(expiresAt).toLocaleString()))
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /copiar código/i })).toBeInTheDocument();
  });

  it("WHEN the copy button is clicked THEN it copies the code and calls onCopy once", async () => {
    const onCopy = vi.fn();
    render(<LinkCodeCard code="ABC123" expiresAt="2026-08-09T12:00:00Z" onCopy={onCopy} />);

    await userEvent.click(screen.getByRole("button", { name: /copiar código/i }));

    expect(writeText).toHaveBeenCalledWith("ABC123");
    expect(onCopy).toHaveBeenCalledTimes(1);
  });
});
