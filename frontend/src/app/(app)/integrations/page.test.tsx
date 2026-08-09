import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import IntegrationsPage from "./page";

const mockCreateWhatsAppLinkCode = vi.fn();
const mockCreateTelegramLinkCode = vi.fn();
const mockToastSuccess = vi.fn();

vi.mock("@/lib/integrations", async () => {
  const actual = await vi.importActual<typeof import("@/lib/integrations")>(
    "@/lib/integrations"
  );
  return {
    ...actual,
    createWhatsAppLinkCode: (...args: unknown[]) => mockCreateWhatsAppLinkCode(...args),
    createTelegramLinkCode: (...args: unknown[]) => mockCreateTelegramLinkCode(...args),
  };
});

vi.mock("sonner", () => ({
  toast: { success: (...args: unknown[]) => mockToastSuccess(...args) },
}));

function sectionFor(heading: string): HTMLElement {
  const el = screen.getByRole("heading", { name: heading }).closest("section");
  if (!el) throw new Error(`section for "${heading}" not found`);
  return el as HTMLElement;
}

describe("IntegrationsPage - WhatsApp section (telegram-integration-frontend-registration-task-component-1 unit-3 / REQ-004)", () => {
  const writeText = vi.fn().mockResolvedValue(undefined);

  beforeEach(() => {
    mockCreateWhatsAppLinkCode.mockReset();
    mockCreateTelegramLinkCode.mockReset();
    mockToastSuccess.mockClear();
    writeText.mockClear();
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText },
      configurable: true,
    });
  });

  it("WHEN the user generates and copies a WhatsApp code THEN the flow behaves exactly as before the LinkCodeCard refactor", async () => {
    mockCreateWhatsAppLinkCode.mockResolvedValue({
      code: "WA9Z8Y",
      expires_at: "2026-08-09T12:00:00Z",
    });

    render(<IntegrationsPage />);

    const whatsapp = sectionFor("WhatsApp");
    await userEvent.click(
      within(whatsapp).getByRole("button", { name: /gerar código de vínculo/i })
    );

    expect(mockCreateWhatsAppLinkCode).toHaveBeenCalledTimes(1);
    expect(await within(whatsapp).findByText("WA9Z8Y")).toBeInTheDocument();

    await userEvent.click(
      within(whatsapp).getByRole("button", { name: /copiar código/i })
    );
    expect(writeText).toHaveBeenCalledWith("WA9Z8Y");
    expect(mockToastSuccess).toHaveBeenCalledWith("Código copiado");
  });
});

describe("IntegrationsPage - Telegram section (telegram-integration-frontend-registration-task-page-1 unit-1/2/3 / REQ-001, REQ-002)", () => {
  beforeEach(() => {
    mockCreateWhatsAppLinkCode.mockReset();
    mockCreateTelegramLinkCode.mockReset();
    mockToastSuccess.mockClear();
  });

  it("WHEN the page renders THEN a Telegram section shows the /start <código> instruction and a generate button", () => {
    render(<IntegrationsPage />);

    const telegram = sectionFor("Telegram");
    expect(within(telegram).getByText(/\/start/)).toBeInTheDocument();
    expect(
      within(telegram).getByRole("button", { name: /gerar código de vínculo/i })
    ).toBeInTheDocument();
  });

  it("WHEN the user clicks generate and the request succeeds THEN the Telegram section renders a LinkCodeCard with the returned code", async () => {
    mockCreateTelegramLinkCode.mockResolvedValue({
      code: "TG7F3K",
      expires_at: "2026-08-09T12:10:00Z",
    });

    render(<IntegrationsPage />);

    const telegram = sectionFor("Telegram");
    await userEvent.click(
      within(telegram).getByRole("button", { name: /gerar código de vínculo/i })
    );

    expect(mockCreateTelegramLinkCode).toHaveBeenCalledTimes(1);
    expect(await within(telegram).findByText("TG7F3K")).toBeInTheDocument();
  });

  it("WHEN the request fails THEN the Telegram section shows an inline error and no code card", async () => {
    mockCreateTelegramLinkCode.mockRejectedValue(new Error("Falha ao gerar código"));

    render(<IntegrationsPage />);

    const telegram = sectionFor("Telegram");
    await userEvent.click(
      within(telegram).getByRole("button", { name: /gerar código de vínculo/i })
    );

    expect(await within(telegram).findByRole("alert")).toBeInTheDocument();
    expect(within(telegram).queryByRole("button", { name: /copiar código/i })).toBeNull();
  });
});
