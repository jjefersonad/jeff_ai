import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { InboxPanel } from "./InboxPanel";
import type { Email, EmailAccount } from "@/lib/email";

const mockListEmails = vi.fn();
const mockSearchEmails = vi.fn();
const mockGetEmail = vi.fn();
const mockUpdateEmail = vi.fn();
const mockPush = vi.fn();
const mockReplace = vi.fn();
let mockSearchParams = new URLSearchParams();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush, replace: mockReplace }),
  useSearchParams: () => mockSearchParams,
}));

vi.mock("@/lib/email", async () => {
  const actual = await vi.importActual<typeof import("@/lib/email")>(
    "@/lib/email"
  );
  return {
    ...actual,
    listEmails: (...args: unknown[]) => mockListEmails(...args),
    searchEmails: (...args: unknown[]) => mockSearchEmails(...args),
    getEmail: (...args: unknown[]) => mockGetEmail(...args),
    updateEmail: (...args: unknown[]) => mockUpdateEmail(...args),
  };
});

// matchMedia stub for responsive-aware tests. jsdom does not implement
// matchMedia; we install a minimal stub per describe so each test can
// opt into desktop (matches: true) or mobile (matches: false) mode
// without leaking between tests.
function installMatchMedia(matches: boolean) {
  const listeners: Array<(e: MediaQueryListEvent) => void> = [];
  const mql: MediaQueryList = {
    matches,
    media: "(min-width: 768px)",
    onchange: null,
    addEventListener: (_: string, l: (e: MediaQueryListEvent) => void) => {
      listeners.push(l);
    },
    removeEventListener: (_: string, l: (e: MediaQueryListEvent) => void) => {
      const i = listeners.indexOf(l);
      if (i >= 0) listeners.splice(i, 1);
    },
    addListener: (l: (e: MediaQueryListEvent) => void) => listeners.push(l),
    removeListener: (l: (e: MediaQueryListEvent) => void) => {
      const i = listeners.indexOf(l);
      if (i >= 0) listeners.splice(i, 1);
    },
    dispatchEvent: () => true,
  };
  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    writable: true,
    value: () => mql,
  });
  return { mql, listeners };
}

const account: EmailAccount = {
  id: "acc-1",
  user_id: "user-1",
  provider: "imap",
  display_name: "acc@example.com",
  status: "connected",
  last_synced_at: null,
  is_active: true,
  created_at: "2026-08-01T00:00:00Z",
  updated_at: "2026-08-01T00:00:00Z",
};

beforeEach(() => {
  mockPush.mockReset();
  mockReplace.mockReset();
  mockSearchParams = new URLSearchParams();
});

describe("InboxPanel toolbar (email-inbox-ux-improvements-task-toolbar-1 unit-1/unit-2 / REQ-007)", () => {
  beforeEach(() => {
    mockListEmails.mockReset();
    mockSearchEmails.mockReset();
    mockGetEmail.mockReset();
    mockUpdateEmail.mockReset();
    mockListEmails.mockResolvedValue([]);
  });

  it("unit-1: renders 'Nova mensagem' next to 'Buscar' and calls onCompose with no prefill when clicked", async () => {
    const onCompose = vi.fn();
    render(
      <InboxPanel
        accounts={[account]}
        onCompose={onCompose}
      />
    );

    const searchButton = await screen.findByRole("button", { name: /buscar/i });
    const composeButton = screen.getByRole("button", {
      name: /nova mensagem/i,
    });

    expect(searchButton.parentElement).toBe(composeButton.parentElement);

    await userEvent.click(composeButton);
    expect(onCompose).toHaveBeenCalledTimes(1);
    expect(onCompose).toHaveBeenCalledWith();
  });

  it("unit-2: 'Nova mensagem' is disabled when accounts is empty", async () => {
    render(
      <InboxPanel
        accounts={[]}
        onCompose={vi.fn()}
      />
    );

    const composeButton = await screen.findByRole("button", {
      name: /nova mensagem/i,
    });
    expect(composeButton).toBeDisabled();
  });
});

function emailFor(id: string, extras: Partial<Email> = {}): Email {
  return {
    id,
    email_account_id: "acc-1",
    message_id: `<${id}@example.com>`,
    thread_id: null,
    folder: "Inbox",
    from_address: "sender@example.com",
    from_name: null,
    to_addresses: [],
    cc_addresses: [],
    bcc_addresses: [],
    subject: "Assunto de teste",
    body_html: null,
    body_text: "corpo",
    is_read: false,
    is_starred: false,
    has_attachments: false,
    contact_id: null,
    received_at: "2026-08-11T14:30:00Z",
    created_at: "2026-08-11T14:30:00Z",
    ...extras,
  };
}

describe("InboxPanel list columns (email-inbox-ux-improvements-task-list-1 unit-1..5 / REQ-008)", () => {
  beforeEach(() => {
    mockListEmails.mockReset();
    mockSearchEmails.mockReset();
    mockGetEmail.mockReset();
    mockUpdateEmail.mockReset();
  });

  it("unit-1: unread row's Status column shows the closed-envelope (Mail) icon", async () => {
    mockListEmails.mockResolvedValue([emailFor("e1", { is_read: false })]);
    render(
      <InboxPanel
        accounts={[account]}
        onCompose={vi.fn()}
      />
    );

    // The table row and the mobile card both have role="button" and
    // an aria-label containing the subject; disambiguate by tag.
    const rows = await screen.findAllByRole("button", {
      name: /assunto de teste/i,
    });
    const row = rows.find((el) => el.tagName === "TR") as HTMLElement;
    expect(
      within(row).getByRole("img", { name: "Não lido" })
    ).toBeInTheDocument();
    expect(
      within(row).queryByRole("img", { name: "Lido" })
    ).not.toBeInTheDocument();
  });

  it("unit-2: read row's Status column shows the open-envelope (MailOpen) icon", async () => {
    mockListEmails.mockResolvedValue([emailFor("e1", { is_read: true })]);
    render(
      <InboxPanel
        accounts={[account]}
        onCompose={vi.fn()}
      />
    );

    const rows = await screen.findAllByRole("button", {
      name: /assunto de teste/i,
    });
    const row = rows.find((el) => el.tagName === "TR") as HTMLElement;
    expect(within(row).getByRole("img", { name: "Lido" })).toBeInTheDocument();
    expect(
      within(row).queryByRole("img", { name: "Não lido" })
    ).not.toBeInTheDocument();
  });

  it("unit-3: Nome/email column falls back to from_address when from_name is null", async () => {
    mockListEmails.mockResolvedValue([
      emailFor("e1", { from_name: null, from_address: "no-name@example.com" }),
    ]);
    render(
      <InboxPanel
        accounts={[account]}
        onCompose={vi.fn()}
      />
    );

    const rows = await screen.findAllByRole("button", {
      name: /assunto de teste/i,
    });
    const row = rows.find((el) => el.tagName === "TR") as HTMLElement;
    expect(within(row).getByText("no-name@example.com")).toBeInTheDocument();
  });

  it("unit-4: Nome/email column shows from_name when known", async () => {
    mockListEmails.mockResolvedValue([
      emailFor("e1", {
        from_name: "Ana Silva",
        from_address: "ana@example.com",
      }),
    ]);
    render(
      <InboxPanel
        accounts={[account]}
        onCompose={vi.fn()}
      />
    );

    const rows = await screen.findAllByRole("button", {
      name: /assunto de teste/i,
    });
    const row = rows.find((el) => el.tagName === "TR") as HTMLElement;
    expect(within(row).getByText("Ana Silva")).toBeInTheDocument();
    expect(within(row).queryByText("ana@example.com")).not.toBeInTheDocument();
  });

  it("unit-5: Data column shows a formatted date and time for received_at", async () => {
    const receivedAt = "2026-08-11T14:30:00Z";
    mockListEmails.mockResolvedValue([
      emailFor("e1", { received_at: receivedAt }),
    ]);
    render(
      <InboxPanel
        accounts={[account]}
        onCompose={vi.fn()}
      />
    );

    const expected = new Date(receivedAt).toLocaleString();
    const rows = await screen.findAllByRole("button", {
      name: /assunto de teste/i,
    });
    const row = rows.find((el) => el.tagName === "TR") as HTMLElement;
    expect(within(row).getByText(expected)).toBeInTheDocument();
  });
});

describe("InboxPanel list layout (email-inbox-ux-improvements-task-modal-1 unit-2 / REQ-009)", () => {
  beforeEach(() => {
    mockListEmails.mockReset();
    mockSearchEmails.mockReset();
    mockGetEmail.mockReset();
    mockUpdateEmail.mockReset();
  });

  it("unit-2: with no reading page open, the list has no split-pane grid wrapper and no read-pane markup", async () => {
    mockListEmails.mockResolvedValue([emailFor("e1")]);
    const { container } = render(
      <InboxPanel
        accounts={[account]}
        onCompose={vi.fn()}
      />
    );

    await screen.findAllByRole("button", { name: /assunto de teste/i });

    expect(
      container.querySelector('[class*="grid-cols-[2fr_3fr]"]')
    ).toBeNull();
    expect(
      screen.queryByText("Selecione um e-mail para ler.")
    ).not.toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// email-inbox-responsiveness — breakpoint and per-card content
// (task-breakpoint-1 / REQ-011)
// ---------------------------------------------------------------------------
describe("InboxPanel responsive list (email-inbox-responsiveness-task-breakpoint-1 / REQ-011)", () => {
  let originalMatchMedia: typeof window.matchMedia | undefined;

  beforeEach(() => {
    mockListEmails.mockReset();
    mockSearchEmails.mockReset();
    mockGetEmail.mockReset();
    mockUpdateEmail.mockReset();
    mockListEmails.mockResolvedValue([]);
    originalMatchMedia = window.matchMedia;
  });

  afterEach(() => {
    if (originalMatchMedia === undefined) {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      delete (window as any).matchMedia;
    } else {
      Object.defineProperty(window, "matchMedia", {
        configurable: true,
        writable: true,
        value: originalMatchMedia,
      });
    }
  });

  it("unit-1: each mobile card renders the same four data points as the desktop row (Status icon, sender, subject, date+time)", async () => {
    const receivedAt = "2026-08-11T14:30:00Z";
    const expected = new Date(receivedAt).toLocaleString();
    installMatchMedia(false);
    mockListEmails.mockResolvedValue([
      emailFor("e1", {
        from_name: "Ana Silva",
        from_address: "ana@example.com",
        subject: "Assunto de teste",
        is_read: false,
        received_at: receivedAt,
      }),
    ]);

    const { container } = render(
      <InboxPanel
        accounts={[account]}
        onCompose={vi.fn()}
      />
    );

    // Wait for the list to render the card (listEmails is async).
    await screen.findByTestId("email-card");

    // The card list is the one with email-card data-testids.
    const cards = container.querySelectorAll('[data-testid="email-card"]');
    expect(cards).toHaveLength(1);
    const card = cards[0];
    // Four data points:
    // (a) Status icon — Mail (closed envelope) for unread.
    expect(
      within(card as HTMLElement).getByRole("img", { name: "Não lido" })
    ).toBeInTheDocument();
    // (b) Sender (from_name).
    expect(
      within(card as HTMLElement).getByText("Ana Silva")
    ).toBeInTheDocument();
    // (c) Subject.
    expect(
      within(card as HTMLElement).getByText("Assunto de teste")
    ).toBeInTheDocument();
    // (d) Date+time (locale-formatted).
    expect(within(card as HTMLElement).getByText(expected)).toBeInTheDocument();
  });

  it("unit-2: at the md breakpoint and above, the table is in the wrapper with `hidden md:block`; the card list has `md:hidden`", async () => {
    installMatchMedia(true);
    mockListEmails.mockResolvedValue([emailFor("e1")]);

    const { container } = render(
      <InboxPanel
        accounts={[account]}
        onCompose={vi.fn()}
      />
    );
    await screen.findAllByRole("button", { name: /assunto de teste/i });

    const table = container.querySelector("table");
    expect(table).not.toBeNull();
    // The desktop wrapper carries `hidden md:block` so the table is
    // visually hidden below 768px and shown at md+.
    const tableWrapper = table!.parentElement!;
    expect(tableWrapper.className).toMatch(/\bhidden\b/);
    expect(tableWrapper.className).toMatch(/\bmd:block\b/);

    const cardList = container.querySelector(
      '[data-testid="email-card"]'
    )?.parentElement;
    expect(cardList).not.toBeNull();
    expect((cardList as HTMLElement).className).toMatch(/\bmd:hidden\b/);
  });

  it("unit-3: mobile card is keyboard-activatable (Enter and Space navigate to the reading page)", async () => {
    installMatchMedia(false);
    const email = emailFor("e1", { subject: "Assunto de teste" });
    mockListEmails.mockResolvedValue([email]);

    const user = userEvent.setup();
    render(
      <InboxPanel
        accounts={[account]}
        onCompose={vi.fn()}
      />
    );

    const card = (await screen.findByTestId("email-card")) as HTMLElement;
    card.focus();
    await user.keyboard("{Enter}");
    expect(mockPush).toHaveBeenCalled();
    expect(String(mockPush.mock.calls[0][0])).toMatch(/^\/email\/e1(\?|$)/);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    mockPush.mockClear();
    card.focus();
    await user.keyboard(" ");
    expect(mockPush).toHaveBeenCalled();
    expect(String(mockPush.mock.calls[0][0])).toMatch(/^\/email\/e1(\?|$)/);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("unit-4: mobile card's aria-label is distinct from the desktop row's, so role-based queries don't throw 'multiple matches'", async () => {
    installMatchMedia(false);
    mockListEmails.mockResolvedValue([emailFor("e1")]);

    const { container } = render(
      <InboxPanel
        accounts={[account]}
        onCompose={vi.fn()}
      />
    );
    await screen.findByTestId("email-card");

    const card = container.querySelector(
      '[data-testid="email-card"]'
    ) as HTMLElement;
    const cardLabel = card.getAttribute("aria-label");
    // The card MUST have its own aria-label distinct from the desktop row.
    expect(cardLabel).toBeTruthy();
    expect(cardLabel).toMatch(/Abrir e-mail/i);

    // The desktop row still uses the previous label.
    const row = container.querySelector(
      'tr[role="button"]'
    ) as HTMLElement | null;
    if (row) {
      expect(row.getAttribute("aria-label")).not.toBe(cardLabel);
    }
  });
});

describe("InboxPanel list layout (melhorar-visualizacao-de-emails-task-inbox-2 unit-3 / REQ-015)", () => {
  beforeEach(() => {
    mockListEmails.mockReset();
    mockSearchEmails.mockReset();
    mockGetEmail.mockReset();
    mockUpdateEmail.mockReset();
  });

  it("unit-3: with no email open, the list is not a split-pane grid", async () => {
    mockListEmails.mockResolvedValue([emailFor("e1")]);
    const { container } = render(
      <InboxPanel
        accounts={[account]}
        onCompose={vi.fn()}
      />
    );

    await screen.findAllByRole("button", { name: /assunto de teste/i });

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(
      container.querySelector('[class*="grid-cols-[2fr_3fr]"]')
    ).toBeNull();
    expect(container.querySelector('[class*="grid-cols-[1fr_"]')).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// email-inbox-responsiveness — toolbar wrapping at xs (task-toolbar-1 / REQ-012)
// ---------------------------------------------------------------------------
// jsdom does not lay out, so we cannot assert on getBoundingClientRect() or
// document.body.scrollWidth. Instead, we assert on the Tailwind class
// contracts that prevent horizontal page scroll on narrow viewports:
//   - the inner toolbar group must allow wrapping (flex-wrap, min-w-0),
//   - the search input must allow shrinking (min-w-0) with a bounded
//     width (w-64 on sm+; on xs it shrinks via the parent's flex-wrap),
//   - the "Nova mensagem" button must drop below other controls on xs
//     (w-full) and right-align on sm+ (sm:w-auto).
describe("InboxPanel responsive toolbar (email-inbox-responsiveness-task-toolbar-1 / REQ-012)", () => {
  beforeEach(() => {
    mockListEmails.mockReset();
    mockSearchEmails.mockReset();
    mockGetEmail.mockReset();
    mockUpdateEmail.mockReset();
    mockListEmails.mockResolvedValue([]);
  });

  it("unit-1: 'Nova mensagem' button carries w-full (xs) and sm:w-auto (sm+) so it does not push itself off-screen at 375px", async () => {
    render(
      <InboxPanel
        accounts={[account]}
        onCompose={vi.fn()}
      />
    );
    const composeButton = await screen.findByRole("button", {
      name: /nova mensagem/i,
    });
    // Full width on xs, inline width from sm up. The combination is what
    // lets the button fall onto its own line on narrow viewports and
    // float right on wider ones, preventing horizontal page scroll.
    expect(composeButton.className).toMatch(/\bw-full\b/);
    expect(composeButton.className).toMatch(/\bsm:w-auto\b/);
  });

  it("unit-2: the inner toolbar group allows wrapping (flex-wrap, min-w-0) and the search input carries min-w-0 with a bounded width", async () => {
    const { container } = render(
      <InboxPanel
        accounts={[account]}
        onCompose={vi.fn()}
      />
    );
    await screen.findByRole("button", { name: /buscar/i });

    // The search input's <Input> component renders a real <input>. The
    // inner toolbar group is the parent <div> containing the search
    // input and the Buscar button.
    const searchInput = screen.getByLabelText(
      /buscar e-mails/i
    ) as HTMLInputElement;
    // min-w-0 lets the input shrink inside its flex parent; the previous
    // max-w-sm forced horizontal overflow at 375px, so the test asserts
    // a bounded-width class (w-64 or w-full, etc.) is in use instead.
    expect(searchInput.className).toMatch(/\bmin-w-0\b/);
    expect(searchInput.className).toMatch(/\bw-\d+\b/);
    // It must NOT carry the previous max-w-sm, which on a 375px viewport
    // would force horizontal overflow.
    expect(searchInput.className).not.toMatch(/\bmax-w-sm\b/);

    // The inner toolbar group is the parent of the search input.
    const innerGroup = searchInput.parentElement as HTMLElement;
    expect(innerGroup.className).toMatch(/\bflex-wrap\b/);
    expect(innerGroup.className).toMatch(/\bmin-w-0\b/);
    // Container variable intentionally unused but kept for symmetry with
    // the visual review checklist.
    void container;
  });
});

describe("InboxPanel navigation (email-detail-full-page-task-inbox-1)", () => {
  let originalMatchMedia: typeof window.matchMedia | undefined;

  beforeEach(() => {
    mockListEmails.mockReset();
    mockSearchEmails.mockReset();
    mockGetEmail.mockReset();
    mockUpdateEmail.mockReset();
    originalMatchMedia = window.matchMedia;
  });

  afterEach(() => {
    if (originalMatchMedia === undefined) {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      delete (window as any).matchMedia;
    } else {
      Object.defineProperty(window, "matchMedia", {
        configurable: true,
        writable: true,
        value: originalMatchMedia,
      });
    }
  });

  it("unit-1: row click navigates and does not open a detail Dialog", async () => {
    const email = emailFor("e1", {
      subject: "Assunto do email",
      body_text: "Corpo completo do email",
    });
    mockListEmails.mockResolvedValue([email]);
    render(
      <InboxPanel
        accounts={[account]}
        onCompose={vi.fn()}
      />
    );

    const rows = await screen.findAllByRole("button", {
      name: /assunto do email/i,
    });
    const row = rows.find((el) => el.tagName === "TR") as HTMLElement;
    await userEvent.click(row);

    expect(mockPush).toHaveBeenCalled();
    const href = String(mockPush.mock.calls[0][0]);
    expect(href).toMatch(/^\/email\/e1(\?|$)/);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(
      screen.queryByText("Corpo completo do email")
    ).not.toBeInTheDocument();
  });

  it("unit-2: list is full width with no split pane or detail dialog", async () => {
    mockListEmails.mockResolvedValue([emailFor("e1")]);
    const { container } = render(
      <InboxPanel
        accounts={[account]}
        onCompose={vi.fn()}
      />
    );

    await screen.findAllByRole("button", { name: /assunto de teste/i });

    expect(container.innerHTML).not.toMatch(/grid-cols-\[2fr_3fr\]/);
    expect(
      screen.queryByText("Selecione um e-mail para ler.")
    ).not.toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.queryByTitle("Corpo do e-mail")).not.toBeInTheDocument();
  });

  it("unit-3: mobile card Enter/Space navigates to reading page", async () => {
    installMatchMedia(false);
    const email = emailFor("e1", { subject: "Assunto de teste" });
    mockListEmails.mockResolvedValue([email]);

    const user = userEvent.setup();
    render(
      <InboxPanel
        accounts={[account]}
        onCompose={vi.fn()}
      />
    );

    const card = (await screen.findByTestId("email-card")) as HTMLElement;
    card.focus();
    await user.keyboard("{Enter}");
    expect(mockPush).toHaveBeenCalled();
    expect(String(mockPush.mock.calls[0][0])).toMatch(/^\/email\/e1(\?|$)/);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    mockPush.mockClear();
    card.focus();
    await user.keyboard(" ");
    expect(mockPush).toHaveBeenCalled();
    expect(String(mockPush.mock.calls[0][0])).toMatch(/^\/email\/e1(\?|$)/);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("unit-4: list filters are query params copied onto the reading href", async () => {
    mockSearchParams = new URLSearchParams("folder=Sent&account=acc-1&q=hello");
    mockListEmails.mockResolvedValue([emailFor("e1")]);
    mockSearchEmails.mockResolvedValue([emailFor("e1")]);

    render(
      <InboxPanel
        accounts={[account]}
        onCompose={vi.fn()}
      />
    );

    const rows = await screen.findAllByRole("button", {
      name: /assunto de teste/i,
    });
    const row = rows.find((el) => el.tagName === "TR") as HTMLElement;
    await userEvent.click(row);

    expect(mockPush).toHaveBeenCalled();
    const href = String(mockPush.mock.calls[0][0]);
    const params = new URL(href, "http://localhost").searchParams;
    expect(params.get("folder")).toBe("Sent");
    expect(params.get("account")).toBe("acc-1");
    expect(params.get("q")).toBe("hello");
  });
});
