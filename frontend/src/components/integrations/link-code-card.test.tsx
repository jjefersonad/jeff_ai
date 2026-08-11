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

describe("LinkCodeCard deep link (channel-link-wiring-task-link-code-card-1 unit-2/3/4 / channel-link-deep-links REQ-001/002/003)", () => {
  const writeText = vi.fn().mockResolvedValue(undefined);

  beforeEach(() => {
    writeText.mockClear();
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText },
      configurable: true,
    });
  });

  it("WHEN deepLinkHref is provided THEN renders a link with that href opening in a new tab", () => {
    render(
      <LinkCodeCard
        code="ABC123"
        expiresAt="2026-08-09T12:00:00Z"
        deepLinkHref="https://t.me/jeff_ai_bot?start=ABC123"
      />
    );

    const link = screen.getByRole("link", { name: /abrir chat/i });
    expect(link).toHaveAttribute("href", "https://t.me/jeff_ai_bot?start=ABC123");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link.getAttribute("rel")).toContain("noopener");
  });

  it("WHEN deepLinkHref is undefined THEN renders no deep-link control", () => {
    render(<LinkCodeCard code="ABC123" expiresAt="2026-08-09T12:00:00Z" />);

    expect(screen.queryByRole("link", { name: /abrir chat/i })).not.toBeInTheDocument();
  });

  it("WHEN deepLinkHref is provided THEN the copy button remains present and functional", async () => {
    render(
      <LinkCodeCard
        code="ABC123"
        expiresAt="2026-08-09T12:00:00Z"
        deepLinkHref="https://wa.me/5511999999999?text=ABC123"
      />
    );

    const copyButton = screen.getByRole("button", { name: /copiar código/i });
    expect(copyButton).toBeInTheDocument();

    await userEvent.click(copyButton);
    expect(writeText).toHaveBeenCalledWith("ABC123");
  });
});
