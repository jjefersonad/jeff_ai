import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { AddIntegrationDialog } from "./add-integration-dialog";

const mockCreateWhatsAppLinkCode = vi.fn();
const mockCreateTelegramLinkCode = vi.fn();
const mockGetChannelLinkConfig = vi.fn();

vi.mock("@/lib/integrations", async () => {
  const actual = await vi.importActual<typeof import("@/lib/integrations")>(
    "@/lib/integrations"
  );
  return {
    ...actual,
    createWhatsAppLinkCode: (...args: unknown[]) => mockCreateWhatsAppLinkCode(...args),
    createTelegramLinkCode: (...args: unknown[]) => mockCreateTelegramLinkCode(...args),
    getChannelLinkConfig: (...args: unknown[]) => mockGetChannelLinkConfig(...args),
  };
});

vi.mock("sonner", () => ({
  toast: { success: vi.fn() },
}));

function renderDialog(props: Partial<React.ComponentProps<typeof AddIntegrationDialog>> = {}) {
  const onOpenChange = vi.fn();
  render(
    <AddIntegrationDialog open onOpenChange={onOpenChange} {...props} />
  );
  return { onOpenChange };
}

describe("AddIntegrationDialog (user-integrations-list-delete-task-add-dialog-1 unit-1..4 / add-integration-modal REQ-001/002/003)", () => {
  beforeEach(() => {
    mockCreateWhatsAppLinkCode.mockReset();
    mockCreateTelegramLinkCode.mockReset();
    mockGetChannelLinkConfig.mockReset();
    mockGetChannelLinkConfig.mockResolvedValue({
      telegram_bot_username: null,
      whatsapp_business_number: null,
    });
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText: vi.fn() },
      configurable: true,
    });
  });

  it("WHEN opened THEN renders a type picker with WhatsApp and Telegram options, no generate flow yet", () => {
    renderDialog();

    const dialog = within(screen.getByRole("dialog"));
    expect(dialog.getByRole("button", { name: /whatsapp/i })).toBeInTheDocument();
    expect(dialog.getByRole("button", { name: /telegram/i })).toBeInTheDocument();
    expect(
      dialog.queryByRole("button", { name: /gerar código de vínculo/i })
    ).not.toBeInTheDocument();
  });

  it("WHEN WhatsApp is picked and generated THEN calls createWhatsAppLinkCode and renders LinkCodeCard", async () => {
    mockCreateWhatsAppLinkCode.mockResolvedValue({
      code: "WA1A2B",
      expires_at: "2026-08-09T12:00:00Z",
    });
    renderDialog();

    const dialog = within(screen.getByRole("dialog"));
    await userEvent.click(dialog.getByRole("button", { name: /whatsapp/i }));
    await userEvent.click(dialog.getByRole("button", { name: /gerar código de vínculo/i }));

    expect(mockCreateWhatsAppLinkCode).toHaveBeenCalledTimes(1);
    expect(await dialog.findByText("WA1A2B")).toBeInTheDocument();
  });

  it("WHEN Telegram is picked and generated THEN calls createTelegramLinkCode and renders LinkCodeCard", async () => {
    mockCreateTelegramLinkCode.mockResolvedValue({
      code: "TG3C4D",
      expires_at: "2026-08-09T12:10:00Z",
    });
    renderDialog();

    const dialog = within(screen.getByRole("dialog"));
    await userEvent.click(dialog.getByRole("button", { name: /telegram/i }));
    await userEvent.click(dialog.getByRole("button", { name: /gerar código de vínculo/i }));

    expect(mockCreateTelegramLinkCode).toHaveBeenCalledTimes(1);
    expect(await dialog.findByText("TG3C4D")).toBeInTheDocument();
  });

  it("WHEN reopened after a previous pick/generate THEN resets to the type picker with no leftover state", async () => {
    mockCreateWhatsAppLinkCode.mockResolvedValue({
      code: "WA1A2B",
      expires_at: "2026-08-09T12:00:00Z",
    });
    const onOpenChange = vi.fn();
    const { rerender } = render(
      <AddIntegrationDialog open onOpenChange={onOpenChange} />
    );

    let dialog = within(screen.getByRole("dialog"));
    await userEvent.click(dialog.getByRole("button", { name: /whatsapp/i }));
    await userEvent.click(dialog.getByRole("button", { name: /gerar código de vínculo/i }));
    expect(await dialog.findByText("WA1A2B")).toBeInTheDocument();

    rerender(<AddIntegrationDialog open={false} onOpenChange={onOpenChange} />);
    rerender(<AddIntegrationDialog open onOpenChange={onOpenChange} />);

    dialog = within(screen.getByRole("dialog"));
    expect(dialog.getByRole("button", { name: /whatsapp/i })).toBeInTheDocument();
    expect(dialog.getByRole("button", { name: /telegram/i })).toBeInTheDocument();
    expect(dialog.queryByText("WA1A2B")).not.toBeInTheDocument();
  });
});

describe("AddIntegrationDialog deep link wiring (channel-link-wiring-task-dialog-wiring-1 unit-1..4 / add-integration-modal REQ-002, channel-link-deep-links REQ-002, design Decision 5)", () => {
  beforeEach(() => {
    mockCreateWhatsAppLinkCode.mockReset();
    mockCreateTelegramLinkCode.mockReset();
    mockGetChannelLinkConfig.mockReset();
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText: vi.fn() },
      configurable: true,
    });
  });

  it("WHEN WhatsApp is generated and whatsapp_business_number is configured THEN LinkCodeCard gets the wa.me deep link", async () => {
    mockGetChannelLinkConfig.mockResolvedValue({
      telegram_bot_username: null,
      whatsapp_business_number: "5511999999999",
    });
    mockCreateWhatsAppLinkCode.mockResolvedValue({
      code: "WA1A2B",
      expires_at: "2026-08-09T12:00:00Z",
    });
    renderDialog();

    const dialog = within(screen.getByRole("dialog"));
    await userEvent.click(dialog.getByRole("button", { name: /whatsapp/i }));
    await userEvent.click(dialog.getByRole("button", { name: /gerar código de vínculo/i }));
    await dialog.findByText("WA1A2B");

    const link = await dialog.findByRole("link", { name: /abrir chat/i });
    expect(link).toHaveAttribute("href", "https://wa.me/5511999999999?text=WA1A2B");
  });

  it("WHEN Telegram is generated and telegram_bot_username is configured THEN LinkCodeCard gets the t.me deep link", async () => {
    mockGetChannelLinkConfig.mockResolvedValue({
      telegram_bot_username: "jeff_ai_bot",
      whatsapp_business_number: null,
    });
    mockCreateTelegramLinkCode.mockResolvedValue({
      code: "TG3C4D",
      expires_at: "2026-08-09T12:10:00Z",
    });
    renderDialog();

    const dialog = within(screen.getByRole("dialog"));
    await userEvent.click(dialog.getByRole("button", { name: /telegram/i }));
    await userEvent.click(dialog.getByRole("button", { name: /gerar código de vínculo/i }));
    await dialog.findByText("TG3C4D");

    const link = await dialog.findByRole("link", { name: /abrir chat/i });
    expect(link).toHaveAttribute("href", "https://t.me/jeff_ai_bot?start=TG3C4D");
  });

  it("WHEN the config is missing or the fetch fails THEN no deep link renders and code generation is unaffected", async () => {
    mockGetChannelLinkConfig.mockRejectedValue(new Error("network down"));
    mockCreateWhatsAppLinkCode.mockResolvedValue({
      code: "WA1A2B",
      expires_at: "2026-08-09T12:00:00Z",
    });
    renderDialog();

    const dialog = within(screen.getByRole("dialog"));
    await userEvent.click(dialog.getByRole("button", { name: /whatsapp/i }));
    await userEvent.click(dialog.getByRole("button", { name: /gerar código de vínculo/i }));

    expect(await dialog.findByText("WA1A2B")).toBeInTheDocument();
    expect(dialog.queryByRole("link", { name: /abrir chat/i })).not.toBeInTheDocument();
  });

  it("WHEN the dialog is opened, closed, and reopened THEN getChannelLinkConfig is called exactly once", async () => {
    mockGetChannelLinkConfig.mockResolvedValue({
      telegram_bot_username: null,
      whatsapp_business_number: null,
    });
    const onOpenChange = vi.fn();
    const { rerender } = render(<AddIntegrationDialog open onOpenChange={onOpenChange} />);

    await screen.findByRole("dialog");
    expect(mockGetChannelLinkConfig).toHaveBeenCalledTimes(1);

    rerender(<AddIntegrationDialog open={false} onOpenChange={onOpenChange} />);
    rerender(<AddIntegrationDialog open onOpenChange={onOpenChange} />);
    rerender(<AddIntegrationDialog open={false} onOpenChange={onOpenChange} />);
    rerender(<AddIntegrationDialog open onOpenChange={onOpenChange} />);

    expect(mockGetChannelLinkConfig).toHaveBeenCalledTimes(1);
  });
});
