/**
 * Tests for the `mode="edit"` extension of `ConnectAccountDialog`
 * (email-account-edit-connection-task-frontend-form-1) and the
 * "Continuar com Google" OAuth entry point
 * (gmail-account-oauth-connection-task-frontend-1-unit-1).
 *
 * The dialog is reused for both the create flow and the new connection-
 * edit flow. In edit mode the form is prefilled with the current
 * connection settings, both password fields start blank, and a helper
 * text under each password explains "leave blank to keep current".
 * Submission in edit mode calls the new
 * `updateEmailAccountConfig(id, payload)` client (PATCH) instead of
 * `connectEmailAccount` (POST).
 *
 * In create mode the dialog now also exposes a "Continuar com Google"
 * button that delegates to `startGmailOAuth()` (POST
 * /api/email/accounts/gmail/authorize) and navigates `window.location` to
 * the returned `authorize_url`. Only `vi.mock("@/lib/email", ...)` is
 * declared here (top-level) and is shared by both describe blocks — a
 * second mock re-declaration in a sibling describe would override the
 * first and break unrelated tests in this file.
 *
 * Mirrors the `vi.mock("@/lib/email", ...)` pattern from
 * `InboxPanel.test.tsx`.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { ConnectAccountDialog } from "./ConnectAccountDialog";
import type { EmailAccount } from "@/lib/email";

const mockUpdateEmailAccountConfig = vi.fn();
const mockConnectEmailAccount = vi.fn();
const mockStartGmailOAuth = vi.fn();

vi.mock("@/lib/email", async () => {
  const actual = await vi.importActual<typeof import("@/lib/email")>("@/lib/email");
  return {
    ...actual,
    connectEmailAccount: (...args: unknown[]) => mockConnectEmailAccount(...args),
    updateEmailAccountConfig: (...args: unknown[]) =>
      mockUpdateEmailAccountConfig(...args),
    startGmailOAuth: (...args: unknown[]) => mockStartGmailOAuth(...args),
  };
});

vi.mock("sonner", () => ({
  toast: { success: vi.fn() },
}));

const PREFILL_ACCOUNT: EmailAccount = {
  id: "acc-1",
  user_id: "user-1",
  provider: "imap",
  display_name: "Trabalho",
  status: "connected",
  last_synced_at: null,
  is_active: true,
  created_at: "2026-08-01T00:00:00Z",
  updated_at: "2026-08-01T00:00:00Z",
};

const PREFILL_CONNECTION = {
  imap_host: "imap.example.com",
  imap_port: 993,
  imap_username: "user@example.com",
  smtp_host: "smtp.example.com",
  smtp_port: 587,
  smtp_username: "user@example.com",
};

function renderEditDialog(
  props: Partial<React.ComponentProps<typeof ConnectAccountDialog>> = {}
) {
  const onOpenChange = vi.fn();
  const onSubmit = props.onSubmit ?? vi.fn();
  render(
    <ConnectAccountDialog
      open
      onOpenChange={onOpenChange}
      onSubmit={onSubmit}
      mode="edit"
      accountId="acc-1"
      prefill={PREFILL_CONNECTION}
      prefillDisplayName={PREFILL_ACCOUNT.display_name}
      {...props}
    />
  );
  return { onOpenChange, onSubmit };
}

describe("ConnectAccountDialog edit mode (email-account-edit-connection-task-frontend-form-1)", () => {
  beforeEach(() => {
    mockUpdateEmailAccountConfig.mockReset();
    mockConnectEmailAccount.mockReset();
  });

  // ----- unit-1 (REQ-001): edit mode prefills + helper text -----
  it("unit-1: edit mode prefills non-secret fields and shows helper text under both passwords", () => {
    renderEditDialog();

    const dialog = within(screen.getByRole("dialog"));
    expect(dialog.getByLabelText(/nome de exibição/i)).toHaveValue("Trabalho");
    // IMAP fields (label has "Host *" prefix; fieldset legend is "IMAP").
    const imapFields = within(
      dialog.getByRole("group", { name: /imap \(recebimento\)/i })
    );
    expect(imapFields.getByLabelText(/^host \*/i)).toHaveValue("imap.example.com");
    expect(imapFields.getByLabelText(/^porta \*/i)).toHaveValue("993");
    expect(imapFields.getByLabelText(/^usuário \*/i)).toHaveValue(
      "user@example.com"
    );
    expect(imapFields.getByLabelText(/^senha/i)).toHaveValue("");
    // SMTP fields.
    const smtpFields = within(
      dialog.getByRole("group", { name: /smtp \(envio\)/i })
    );
    expect(smtpFields.getByLabelText(/^host \*/i)).toHaveValue(
      "smtp.example.com"
    );
    expect(smtpFields.getByLabelText(/^porta \*/i)).toHaveValue("587");
    expect(smtpFields.getByLabelText(/usuário \(opcional\)/i)).toHaveValue(
      "user@example.com"
    );
    expect(smtpFields.getByLabelText(/senha \(opcional\)/i)).toHaveValue("");

    // Helper text (`<p id="email-password-helper">`) is referenced via
    // `aria-describedby` on BOTH password inputs.
    expect(dialog.getByTestId("email-password-helper")).toBeInTheDocument();
    expect(dialog.getByLabelText("Senha")).toHaveAttribute(
      "aria-describedby",
      "email-password-helper"
    );
    expect(dialog.getByLabelText("Senha (opcional)")).toHaveAttribute(
      "aria-describedby",
      "email-password-helper"
    );
  });

  // ----- unit-2 (REQ-001): defensive — partial prefill doesn't crash -----
  it("unit-2: edit mode tolerates a partial prefill without crashing", () => {
    const onOpenChange = vi.fn();
    const onSubmit = vi.fn();
    render(
      <ConnectAccountDialog
        open
        onOpenChange={onOpenChange}
        onSubmit={onSubmit}
        mode="edit"
        accountId="acc-1"
        prefill={{ imap_host: "only-host.example.com" }}
        prefillDisplayName="Partial"
      />
    );
    const dialog = within(screen.getByRole("dialog"));
    expect(dialog.getByLabelText(/nome de exibição/i)).toHaveValue("Partial");
    const imapFields = within(
      dialog.getByRole("group", { name: /imap \(recebimento\)/i })
    );
    expect(imapFields.getByLabelText(/^host \*/i)).toHaveValue(
      "only-host.example.com"
    );
    // The other inputs stay at their sensible defaults (port 993, username
    // empty, both passwords empty).
    expect(imapFields.getByLabelText(/^porta \*/i)).toHaveValue("993");
    expect(imapFields.getByLabelText("Senha")).toHaveValue("");
  });

  // ----- unit-3 (REQ-001): create mode unchanged — no helper text -----
  it("unit-3: create mode does NOT render the 'leave blank to keep current' helper text", () => {
    const onOpenChange = vi.fn();
    const onSubmit = vi.fn();
    render(
      <ConnectAccountDialog
        open
        onOpenChange={onOpenChange}
        onSubmit={onSubmit}
      />
    );
    const dialog = within(screen.getByRole("dialog"));
    expect(
      dialog.queryByText("Deixe em branco para manter a senha atual")
    ).not.toBeInTheDocument();
    // Passwords are still required-looking in create mode (the existing
    // label keeps the asterisk).
    expect(dialog.getByLabelText(/^senha \*$/i)).toBeInTheDocument();
  });

  // ----- unit-4 (REQ-002): successful save closes modal + invalidates -----
  it("unit-4: successful edit submit calls updateEmailAccountConfig and closes the dialog", async () => {
    const onAccountsChanged = vi.fn();
    const onOpenChange = vi.fn();
    mockUpdateEmailAccountConfig.mockResolvedValue({
      ...PREFILL_ACCOUNT,
      display_name: "Trabalho (renamed)",
      updated_at: "2026-08-11T00:00:00Z",
    });
    render(
      <ConnectAccountDialog
        open
        onOpenChange={onOpenChange}
        onSubmit={vi.fn()}
        mode="edit"
        accountId="acc-1"
        prefill={PREFILL_CONNECTION}
        prefillDisplayName={PREFILL_ACCOUNT.display_name}
        onAccountsChanged={onAccountsChanged}
      />
    );

    const dialog = within(screen.getByRole("dialog"));
    await userEvent.clear(dialog.getByLabelText(/nome de exibição/i));
    await userEvent.type(
      dialog.getByLabelText(/nome de exibição/i),
      "Trabalho (renamed)"
    );
    await userEvent.click(dialog.getByRole("button", { name: /salvar/i }));

    await vi.waitFor(() => {
      expect(mockUpdateEmailAccountConfig).toHaveBeenCalledTimes(1);
    });
    expect(mockUpdateEmailAccountConfig).toHaveBeenCalledWith(
      "acc-1",
      expect.objectContaining({
        display_name: "Trabalho (renamed)",
        imap_host: "imap.example.com",
        imap_port: 993,
        imap_username: "user@example.com",
        imap_password: "",
        smtp_host: "smtp.example.com",
        smtp_port: 587,
        smtp_username: "user@example.com",
        smtp_password: "",
      })
    );
    expect(onOpenChange).toHaveBeenCalledWith(false);
    expect(onAccountsChanged).toHaveBeenCalledTimes(1);
  });
});

// ===========================================================================
// gmail-account-oauth-connection-task-frontend-1-unit-1 (REQ-001)
//
// "Continuar com Google" button inside `ConnectAccountDialog`: clicking
// it calls the new `startGmailOAuth()` client (POST
// /api/email/accounts/gmail/authorize) and navigates `window.location` to
// the returned `authorize_url`. Only present in `mode="create"` (in
// `mode="edit"` the account is already connected, so a second OAuth flow
// makes no sense).
// ===========================================================================

describe('ConnectAccountDialog "Continuar com Google" (gmail-account-oauth-connection-task-frontend-1)', () => {
  beforeEach(() => {
    mockStartGmailOAuth.mockReset();
  });

  // ----- unit-1 (REQ-001): clicking "Continuar com Google" calls startGmailOAuth + navigates -----
  it('unit-1: clicking "Continuar com Google" calls startGmailOAuth and navigates window.location to the returned authorize_url', async () => {
    // Mock `window.location` so the dialog can do `window.location.href = ...`
    // without actually navigating the jsdom (which would crash the test).
    const originalLocation = window.location;
    const hrefSetter = vi.fn();
    Object.defineProperty(window, "location", {
      configurable: true,
      value: {
        // jsdom's `Location` is mostly read-only; `href` is settable via
        // assignment but we route through a setter so the test can assert
        // what the dialog tried to navigate to.
        set href(value: string) {
          hrefSetter(value);
        },
        get href() {
          return "";
        },
        assign: vi.fn(),
        replace: vi.fn(),
        reload: vi.fn(),
      },
    });

    mockStartGmailOAuth.mockResolvedValue({
      authorize_url: "https://accounts.google.com/o/oauth2/v2/auth?client_id=stub&state=abc",
    });

    const onOpenChange = vi.fn();
    const onSubmit = vi.fn();
    render(
      <ConnectAccountDialog
        open
        onOpenChange={onOpenChange}
        onSubmit={onSubmit}
      />
    );

    const dialog = within(screen.getByRole("dialog"));
    const googleButton = dialog.getByRole("button", {
      name: /continuar com google/i,
    });
    await userEvent.click(googleButton);

    await vi.waitFor(() => {
      expect(mockStartGmailOAuth).toHaveBeenCalledTimes(1);
    });
    expect(hrefSetter).toHaveBeenCalledWith(
      "https://accounts.google.com/o/oauth2/v2/auth?client_id=stub&state=abc"
    );

    // Restore jsdom's `window.location` for subsequent tests in this file.
    Object.defineProperty(window, "location", {
      configurable: true,
      value: originalLocation,
    });
  });
});
