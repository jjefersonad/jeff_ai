import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import IntegrationsPage from "./page";

const mockListUserIntegrations = vi.fn();
const mockDeleteUserIntegration = vi.fn();
const mockToastSuccess = vi.fn();
const mockToastError = vi.fn();

vi.mock("@/lib/integrations", async () => {
  const actual = await vi.importActual<typeof import("@/lib/integrations")>(
    "@/lib/integrations"
  );
  return {
    ...actual,
    listUserIntegrations: (...args: unknown[]) => mockListUserIntegrations(...args),
    deleteUserIntegration: (...args: unknown[]) => mockDeleteUserIntegration(...args),
  };
});

vi.mock("sonner", () => ({
  toast: {
    success: (...args: unknown[]) => mockToastSuccess(...args),
    error: (...args: unknown[]) => mockToastError(...args),
  },
}));

vi.mock("@/components/integrations/add-integration-dialog", () => ({
  AddIntegrationDialog: ({
    open,
    onOpenChange,
    onLinked,
  }: {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    onLinked?: () => void;
  }) =>
    open ? (
      <div data-testid="add-integration-dialog">
        <button
          type="button"
          onClick={() => {
            onOpenChange(false);
            onLinked?.();
          }}
        >
          fechar-mock
        </button>
      </div>
    ) : null,
}));

function integrationFor(
  id: string,
  integrationType: string,
  extras: Record<string, unknown> = {}
) {
  return {
    id,
    user_id: "u1",
    integration_type: integrationType,
    config: null,
    created_at: "2026-08-01T10:00:00Z",
    updated_at: "2026-08-05T10:00:00Z",
    ...extras,
  };
}

describe("IntegrationsPage - list (user-integrations-list-delete-task-list-1 unit-1..4 / user-integrations-list REQ-001/002)", () => {
  beforeEach(() => {
    mockListUserIntegrations.mockReset();
  });

  it("WHEN entries with known types resolve THEN renders one row per entry with friendly label, timestamps, and Excluir action", async () => {
    mockListUserIntegrations.mockResolvedValue([
      integrationFor("i1", "telegram"),
      integrationFor("i2", "whatsapp_business"),
      integrationFor("i3", "smtp"),
    ]);

    render(<IntegrationsPage />);

    const table = within(await screen.findByRole("table"));
    expect(table.getByText("Telegram")).toBeInTheDocument();
    expect(table.getByText("WhatsApp Business")).toBeInTheDocument();
    expect(table.getByText("SMTP")).toBeInTheDocument();
    expect(table.getAllByRole("button", { name: /excluir/i })).toHaveLength(3);
  });

  it("WHEN an entry has an unknown integration_type THEN it falls back to the raw string without crashing", async () => {
    mockListUserIntegrations.mockResolvedValue([integrationFor("i1", "carrier_pigeon")]);

    render(<IntegrationsPage />);

    const table = within(await screen.findByRole("table"));
    expect(table.getByText("carrier_pigeon")).toBeInTheDocument();
  });

  it("WHEN the list is empty THEN shows the empty-state message and no table", async () => {
    mockListUserIntegrations.mockResolvedValue([]);

    render(<IntegrationsPage />);

    expect(
      await screen.findByText("Você ainda não tem integrações configuradas")
    ).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("WHILE pending THEN shows a loading indicator and never an empty-state message", async () => {
    let resolveFetch: (value: unknown[]) => void = () => {};
    mockListUserIntegrations.mockReturnValue(
      new Promise((resolve) => {
        resolveFetch = resolve;
      })
    );

    render(<IntegrationsPage />);

    expect(
      screen.queryByText("Você ainda não tem integrações configuradas")
    ).not.toBeInTheDocument();
    expect(document.querySelector(".animate-pulse")).not.toBeNull();

    resolveFetch([]);
    expect(
      await screen.findByText("Você ainda não tem integrações configuradas")
    ).toBeInTheDocument();
  });

  it("WHEN the request fails THEN shows a destructive alert message", async () => {
    mockListUserIntegrations.mockRejectedValue(new Error("Falha ao carregar integrações"));

    render(<IntegrationsPage />);

    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});

describe("IntegrationsPage - delete (user-integrations-list-delete-task-delete-1 unit-1..4 / user-integrations-delete REQ-001/002/003)", () => {
  beforeEach(() => {
    mockListUserIntegrations.mockReset();
    mockDeleteUserIntegration.mockReset();
    mockToastSuccess.mockClear();
    mockToastError.mockClear();
  });

  it("WHEN Excluir is clicked THEN a confirmation dialog opens naming the type; Cancelar closes it without an API call", async () => {
    mockListUserIntegrations.mockResolvedValue([integrationFor("i1", "telegram")]);
    render(<IntegrationsPage />);

    const table = within(await screen.findByRole("table"));
    await userEvent.click(table.getByRole("button", { name: /excluir/i }));

    const dialog = within(await screen.findByRole("dialog"));
    expect(dialog.getByRole("heading", { name: "Excluir integração?" })).toBeInTheDocument();
    expect(dialog.getByText(/Telegram/)).toBeInTheDocument();

    await userEvent.click(dialog.getByRole("button", { name: /cancelar/i }));

    expect(
      screen.queryByRole("heading", { name: "Excluir integração?" })
    ).not.toBeInTheDocument();
    expect(mockDeleteUserIntegration).not.toHaveBeenCalled();
    expect(table.getByRole("button", { name: /excluir/i })).toBeInTheDocument();
  });

  it("WHEN the confirmed delete succeeds THEN the dialog closes, the row is removed, and a success toast is shown", async () => {
    mockListUserIntegrations.mockResolvedValue([integrationFor("i1", "telegram")]);
    mockDeleteUserIntegration.mockResolvedValue(undefined);
    render(<IntegrationsPage />);

    const table = within(await screen.findByRole("table"));
    await userEvent.click(table.getByRole("button", { name: /excluir/i }));
    await userEvent.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: /^excluir$/i })
    );

    expect(mockDeleteUserIntegration).toHaveBeenCalledWith("i1");
    expect(
      await screen.findByText("Você ainda não tem integrações configuradas")
    ).toBeInTheDocument();
    expect(mockToastSuccess).toHaveBeenCalledWith("Integração excluída");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("WHEN the confirmed delete fails THEN the dialog closes, the row remains, and an error toast is shown", async () => {
    mockListUserIntegrations.mockResolvedValue([integrationFor("i1", "telegram")]);
    mockDeleteUserIntegration.mockRejectedValue(new Error("network down"));
    render(<IntegrationsPage />);

    let table = within(await screen.findByRole("table"));
    await userEvent.click(table.getByRole("button", { name: /excluir/i }));
    await userEvent.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: /^excluir$/i })
    );

    expect(mockToastError).toHaveBeenCalledWith("Falha ao excluir integração");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    table = within(await screen.findByRole("table"));
    expect(table.getByText("Telegram")).toBeInTheDocument();
  });

  it("WHEN the delete request is in flight THEN the confirm button is disabled and no duplicate call fires", async () => {
    mockListUserIntegrations.mockResolvedValue([integrationFor("i1", "telegram")]);
    let resolveDelete: () => void = () => {};
    mockDeleteUserIntegration.mockReturnValue(
      new Promise<void>((resolve) => {
        resolveDelete = resolve;
      })
    );
    render(<IntegrationsPage />);

    const table = within(await screen.findByRole("table"));
    await userEvent.click(table.getByRole("button", { name: /excluir/i }));
    const confirmButton = within(await screen.findByRole("dialog")).getByRole("button", {
      name: /^excluir$/i,
    });

    await userEvent.click(confirmButton);
    expect(confirmButton).toBeDisabled();

    await userEvent.click(confirmButton);
    expect(mockDeleteUserIntegration).toHaveBeenCalledTimes(1);

    resolveDelete();
  });
});

describe("IntegrationsPage - add integration wiring (user-integrations-list-delete-task-page-1 unit-1/2 / add-integration-modal REQ-001/003)", () => {
  beforeEach(() => {
    mockListUserIntegrations.mockReset();
  });

  it('WHEN "Adicionar integração" is clicked THEN AddIntegrationDialog opens', async () => {
    mockListUserIntegrations.mockResolvedValue([]);
    render(<IntegrationsPage />);
    await screen.findByText("Você ainda não tem integrações configuradas");

    expect(screen.queryByTestId("add-integration-dialog")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /adicionar integração/i }));

    expect(screen.getByTestId("add-integration-dialog")).toBeInTheDocument();
  });

  it("WHEN the dialog closes after generating a code THEN the page re-fetches the list", async () => {
    mockListUserIntegrations.mockResolvedValue([]);
    render(<IntegrationsPage />);
    await screen.findByText("Você ainda não tem integrações configuradas");
    expect(mockListUserIntegrations).toHaveBeenCalledTimes(1);

    await userEvent.click(screen.getByRole("button", { name: /adicionar integração/i }));
    await userEvent.click(screen.getByRole("button", { name: /fechar-mock/i }));

    expect(mockListUserIntegrations).toHaveBeenCalledTimes(2);
  });
});
