/**
 * ContactsPanel WhatsApp opt-in checkbox (saas-empresario-br-task-crm-ui-1).
 *
 * Unit-1 (REQ-006): create/edit form has a native checkbox with pt-BR consent
 * label, default unchecked on create, and no campaign/send WhatsApp button.
 *
 * Unit-2 (REQ-006): checking opt-in and saving includes `whatsapp_opt_in=true`
 * in the write payload and does not send a WhatsApp message.
 */
import { type FormEvent } from "react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { ContactsPanel } from "./ContactsPanel";
import type { CrmContact } from "@/lib/crm";

const mockListContacts = vi.fn();
const mockListFieldDefinitions = vi.fn();
const mockCreateContact = vi.fn();
const mockUpdateContact = vi.fn();
const mockGetContact = vi.fn();
const mockCreateFieldDefinition = vi.fn();
const mockArchiveContact = vi.fn();

vi.mock("@/lib/crm", async () => {
  const actual = await vi.importActual<typeof import("@/lib/crm")>("@/lib/crm");
  return {
    ...actual,
    listContacts: (...args: unknown[]) => mockListContacts(...args),
    listFieldDefinitions: (...args: unknown[]) =>
      mockListFieldDefinitions(...args),
    createContact: (...args: unknown[]) => mockCreateContact(...args),
    updateContact: (...args: unknown[]) => mockUpdateContact(...args),
    getContact: (...args: unknown[]) => mockGetContact(...args),
    createFieldDefinition: (...args: unknown[]) =>
      mockCreateFieldDefinition(...args),
    archiveContact: (...args: unknown[]) => mockArchiveContact(...args),
  };
});

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

function makeContact(overrides: Partial<CrmContact> = {}): CrmContact {
  return {
    id: "contact-1",
    user_id: "user-1",
    name: "Ana Silva",
    email: "ana@acme.com",
    phone: "11999999999",
    company_id: null,
    status: null,
    tags: [],
    city: null,
    state: null,
    whatsapp_opt_in: false,
    custom_values: {},
    archived_at: null,
    created_at: "2026-08-01T00:00:00Z",
    updated_at: "2026-08-01T00:00:00Z",
    ...overrides,
  };
}

function renderPanel() {
  const noopSubmit = (event: FormEvent) => {
    event.preventDefault();
  };
  return render(
    <ContactsPanel
      companies={[]}
      selectedContactId={null}
      onSelectContact={vi.fn()}
      notes={[]}
      noteBody=""
      setNoteBody={vi.fn()}
      onAddNote={noopSubmit}
      onContactsChanged={vi.fn()}
    />
  );
}

const OPT_IN_LABEL = /cliente autorizou contato por whatsapp/i;
const SEND_OR_CAMPAIGN = /enviar whatsapp|disparar|campanha/i;

describe("ContactsPanel WhatsApp opt-in (saas-empresario-br-task-crm-ui-1)", () => {
  let fetchSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    mockListContacts.mockReset();
    mockListFieldDefinitions.mockReset();
    mockCreateContact.mockReset();
    mockUpdateContact.mockReset();
    mockGetContact.mockReset();
    mockCreateFieldDefinition.mockReset();
    mockArchiveContact.mockReset();
    mockListContacts.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 });
    mockListFieldDefinitions.mockResolvedValue([]);
    fetchSpy = vi.spyOn(globalThis, "fetch");
  });

  afterEach(() => {
    fetchSpy.mockRestore();
  });

  it("unit-1: create form has unchecked pt-BR consent checkbox and no send/campaign button", async () => {
    const user = userEvent.setup();
    renderPanel();

    await waitFor(() => {
      expect(mockListContacts).toHaveBeenCalled();
    });

    await user.click(screen.getByRole("button", { name: "Adicionar" }));

    const dialog = await screen.findByRole("dialog");
    expect(
      within(dialog).getByRole("heading", { name: "Novo contato" })
    ).toBeInTheDocument();

    const checkbox = within(dialog).getByRole("checkbox", {
      name: OPT_IN_LABEL,
    });
    expect(checkbox).toBeInstanceOf(HTMLInputElement);
    expect((checkbox as HTMLInputElement).type).toBe("checkbox");
    expect(checkbox).not.toBeChecked();

    expect(
      within(dialog).queryByRole("button", { name: SEND_OR_CAMPAIGN })
    ).not.toBeInTheDocument();
    expect(within(dialog).queryByText(SEND_OR_CAMPAIGN)).not.toBeInTheDocument();
  });

  it("unit-1: edit form has the same pt-BR consent checkbox and no send/campaign button", async () => {
    const user = userEvent.setup();
    const contact = makeContact();
    mockListContacts.mockResolvedValue({
      items: [contact],
      total: 1,
      page: 1,
      page_size: 20,
    });
    mockGetContact.mockResolvedValue(contact);

    renderPanel();

    await waitFor(() => {
      expect(mockListContacts).toHaveBeenCalled();
    });
    await user.click(
      screen.getByRole("button", { name: "Editar Ana Silva" })
    );

    const dialog = await screen.findByRole("dialog");
    expect(
      within(dialog).getByRole("heading", { name: "Editar contato" })
    ).toBeInTheDocument();

    const checkbox = within(dialog).getByRole("checkbox", {
      name: OPT_IN_LABEL,
    });
    expect((checkbox as HTMLInputElement).type).toBe("checkbox");

    expect(
      within(dialog).queryByRole("button", { name: SEND_OR_CAMPAIGN })
    ).not.toBeInTheDocument();
  });

  it("unit-2: checking opt-in and saving includes whatsapp_opt_in=true and does not send WhatsApp", async () => {
    const user = userEvent.setup();
    mockCreateContact.mockResolvedValue(makeContact({ name: "Bruno" }));

    renderPanel();
    await waitFor(() => {
      expect(mockListContacts).toHaveBeenCalled();
    });
    await user.click(screen.getByRole("button", { name: "Adicionar" }));

    const dialog = await screen.findByRole("dialog");
    await user.type(within(dialog).getByLabelText("Nome *"), "Bruno");
    await user.type(within(dialog).getByLabelText("E-mail"), "bruno@acme.com");
    await user.click(
      within(dialog).getByRole("checkbox", { name: OPT_IN_LABEL })
    );
    await user.click(within(dialog).getByRole("button", { name: "Criar" }));

    await waitFor(() => {
      expect(mockCreateContact).toHaveBeenCalled();
    });
    expect(mockCreateContact).toHaveBeenCalledWith(
      expect.objectContaining({ whatsapp_opt_in: true })
    );
    expect(mockCreateContact.mock.calls[0]?.[0]).not.toHaveProperty(
      "created_at"
    );
    expect(mockCreateContact.mock.calls[0]?.[0]).not.toHaveProperty(
      "updated_at"
    );
    expect(fetchSpy).not.toHaveBeenCalled();
  });
});
