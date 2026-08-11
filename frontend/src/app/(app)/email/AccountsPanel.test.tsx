/**
 * Tests for the new "Editar conexão" affordance on each owned email
 * account row in `AccountsPanel` (email-account-edit-connection-task-frontend-ui-1).
 *
 * The new button opens the same `ConnectAccountDialog` (extended in
 * task `frontend-form-1`) with `mode="edit"`, prefilled with the
 * current IMAP/SMTP values, and calls `updateEmailAccountConfig` on
 * save.
 *
 * The metadata-only "Editar conta" dialog (display_name + is_active)
 * already existed; this test covers the NEW button only — the
 * existing pencil icon (which opens the metadata dialog) is still
 * present.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, within, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { AccountsPanel } from "./AccountsPanel";
import type { EmailAccount } from "@/lib/email";

const mockListEmailAccounts = vi.fn();
const mockGetEmailAccount = vi.fn();
const mockUpdateEmailAccountConfig = vi.fn();
const mockUpdateEmailAccount = vi.fn();
const mockDeleteEmailAccount = vi.fn();

vi.mock("@/lib/email", async () => {
  const actual = await vi.importActual<typeof import("@/lib/email")>("@/lib/email");
  return {
    ...actual,
    listEmailAccounts: (...args: unknown[]) => mockListEmailAccounts(...args),
    getEmailAccount: (...args: unknown[]) => mockGetEmailAccount(...args),
    connectEmailAccount: vi.fn(),
    updateEmailAccount: (...args: unknown[]) => mockUpdateEmailAccount(...args),
    updateEmailAccountConfig: (...args: unknown[]) =>
      mockUpdateEmailAccountConfig(...args),
    deleteEmailAccount: (...args: unknown[]) => mockDeleteEmailAccount(...args),
  };
});

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

function makeAccount(overrides: Partial<EmailAccount> = {}): EmailAccount {
  return {
    id: "acc-1",
    user_id: "user-1",
    provider: "imap",
    display_name: "Trabalho",
    status: "connected",
    last_synced_at: null,
    is_active: true,
    created_at: "2026-08-01T00:00:00Z",
    updated_at: "2026-08-01T00:00:00Z",
    imap_host: "imap.example.com",
    imap_port: 993,
    imap_username: "user@example.com",
    smtp_host: "smtp.example.com",
    smtp_port: 587,
    smtp_username: "user@example.com",
    ...overrides,
  };
}

describe("AccountsPanel edit-connection affordance (email-account-edit-connection-task-frontend-ui-1)", () => {
  beforeEach(() => {
    mockListEmailAccounts.mockReset();
    mockGetEmailAccount.mockReset();
    mockUpdateEmailAccountConfig.mockReset();
    mockUpdateEmailAccount.mockReset();
    mockDeleteEmailAccount.mockReset();
  });

  // ----- unit-1 (REQ-001): new "Editar conexão" button visible on each owned row -----
  it("unit-1: each owned row has an 'Editar conexão' button next to Remover", async () => {
    mockListEmailAccounts.mockResolvedValue([
      makeAccount({ id: "acc-1", display_name: "Trabalho" }),
      makeAccount({ id: "acc-2", display_name: "Pessoal" }),
    ]);
    render(<AccountsPanel />);

    // The component renders BOTH a desktop table and a mobile list
    // (CSS-toggle via responsive breakpoints); both have the same
    // aria-labels. We assert the buttons exist at all and are
    // accessible via the aria-label pattern.
    const editarConexaoTrabalho = await screen.findAllByLabelText(
      /editar conexão trabalho/i
    );
    const editarConexaoPessoal = await screen.findAllByLabelText(
      /editar conexão pessoal/i
    );
    expect(editarConexaoTrabalho.length).toBeGreaterThan(0);
    expect(editarConexaoPessoal.length).toBeGreaterThan(0);

    // Sanity: the existing metadata "Editar" + "Remover" actions are still there.
    expect(screen.getAllByLabelText(/editar trabalho/i).length).toBeGreaterThan(0);
    expect(screen.getAllByLabelText(/remover trabalho/i).length).toBeGreaterThan(0);
  });

  // ----- unit-2 (REQ-001): clicking "Editar conexão" opens the modal with mode=edit + prefill -----
  it("unit-2: clicking 'Editar conexão' opens the dialog with mode=edit and prefilled values", async () => {
    const account = makeAccount();
    mockListEmailAccounts.mockResolvedValue([account]);
    render(<AccountsPanel />);

    // Use the desktop-only rendered button (first match).
    const trigger = (await screen.findAllByLabelText(
      /editar conexão trabalho/i
    ))[0];
    await userEvent.click(trigger);

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByLabelText(/nome de exibição/i)).toHaveValue(
      "Trabalho"
    );
    // Os fieldsets do IMAP/SMTP não expõem `role="group"` no DOM do
    // jsdom, então ancoramos pelos ids dos inputs (estáveis no código).
    expect(dialog.querySelector("#email-imap-host")).toHaveValue("imap.example.com");
    expect(dialog.querySelector("#email-imap-port")).toHaveValue("993");
    expect(dialog.querySelector("#email-imap-username")).toHaveValue(
      "user@example.com"
    );
    expect(dialog.querySelector("#email-imap-password")).toHaveValue("");
    expect(dialog.querySelector("#email-smtp-host")).toHaveValue("smtp.example.com");
    expect(dialog.querySelector("#email-smtp-port")).toHaveValue("587");
    // Helper text is present (the dialog is in edit mode).
    expect(
      within(dialog).getByTestId("email-password-helper")
    ).toBeInTheDocument();
    // Title reflects edit mode.
    expect(within(dialog).getByText(/editar conexão de e-mail/i)).toBeInTheDocument();
  });

  // ----- unit-3 (REQ-002): successful save closes modal + invalidates query -----
  it("unit-3: successful save closes the modal and the row reflects the new label without a page reload", async () => {
    const account = makeAccount();
    mockListEmailAccounts.mockResolvedValue([account]);
    mockUpdateEmailAccountConfig.mockResolvedValue({
      ...account,
      display_name: "Trabalho (renamed)",
      updated_at: "2026-08-11T00:00:00Z",
    });

    render(<AccountsPanel />);

    const trigger = (await screen.findAllByLabelText(
      /editar conexão trabalho/i
    ))[0];
    await userEvent.click(trigger);

    const dialog = await screen.findByRole("dialog");
    await userEvent.clear(within(dialog).getByLabelText(/nome de exibição/i));
    await userEvent.type(
      within(dialog).getByLabelText(/nome de exibição/i),
      "Trabalho (renamed)"
    );
    await userEvent.click(within(dialog).getByRole("button", { name: /salvar/i }));

    await waitFor(() => {
      expect(mockUpdateEmailAccountConfig).toHaveBeenCalledTimes(1);
    });
    expect(mockUpdateEmailAccountConfig).toHaveBeenCalledWith(
      "acc-1",
      expect.objectContaining({ display_name: "Trabalho (renamed)" })
    );

    // Modal closed.
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });

    // Row reflects the new label without a page reload — `listEmailAccounts`
    // was called once on mount and never again. The local list was
    // updated in place via setAccounts.
    expect(mockListEmailAccounts).toHaveBeenCalledTimes(1);
    // The renamed label is rendered (the desktop `<span>` carries it).
    expect(
      screen.getAllByText("Trabalho (renamed)").length
    ).toBeGreaterThan(0);
  });
});
