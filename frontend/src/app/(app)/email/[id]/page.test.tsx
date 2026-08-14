import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";

import type { Email } from "@/lib/email";
import { ApiError } from "@/lib/api";

const mockGetEmail = vi.fn();
const mockListEmailAccounts = vi.fn();

let mockParams: { id: string } = { id: "e1" };
let mockSearch = "";

vi.mock("next/navigation", () => ({
  useParams: () => mockParams,
  useSearchParams: () => new URLSearchParams(mockSearch),
}));

vi.mock("next/link", () => ({
  default: ({
    href,
    children,
    ...rest
  }: {
    href: string;
    children: ReactNode;
  }) => (
    <a
      href={href}
      {...rest}
    >
      {children}
    </a>
  ),
}));

vi.mock("@/lib/email", async () => {
  const actual = await vi.importActual<typeof import("@/lib/email")>(
    "@/lib/email"
  );
  return {
    ...actual,
    getEmail: (...args: unknown[]) => mockGetEmail(...args),
    listEmailAccounts: (...args: unknown[]) => mockListEmailAccounts(...args),
  };
});

import EmailDetailPage from "./page";

function sampleEmail(extras: Partial<Email> = {}): Email {
  return {
    id: "e1",
    email_account_id: "acc-1",
    message_id: "<e1@example.com>",
    thread_id: null,
    folder: "Inbox",
    from_address: "sender@example.com",
    from_name: null,
    to_addresses: [],
    cc_addresses: [],
    bcc_addresses: [],
    subject: "Assunto de teste",
    body_html: null,
    body_text: "corpo visível",
    is_read: false,
    is_starred: false,
    has_attachments: false,
    contact_id: null,
    received_at: "2026-08-11T14:30:00Z",
    created_at: "2026-08-11T14:30:00Z",
    ...extras,
  };
}

describe("EmailDetailPage (email-detail-full-page-task-page-1)", () => {
  beforeEach(() => {
    mockGetEmail.mockReset();
    mockListEmailAccounts.mockReset();
    mockParams = { id: "e1" };
    mockSearch = "";
    mockListEmailAccounts.mockResolvedValue([]);
  });

  it("unit-1: owned email loads on the reading page", async () => {
    mockGetEmail.mockResolvedValue(
      sampleEmail({ body_html: "<p>HTML_ONLY_MARKER</p>" })
    );

    render(<EmailDetailPage />);

    expect(
      await screen.findByRole("heading", { name: "Assunto de teste" })
    ).toBeInTheDocument();
    const iframe = await screen.findByTitle("Corpo do e-mail");
    const srcDoc =
      iframe.getAttribute("srcDoc") ?? iframe.getAttribute("srcdoc") ?? "";
    expect(srcDoc).toContain("HTML_ONLY_MARKER");
    expect(mockGetEmail).toHaveBeenCalledWith("e1");
    expect(
      screen.getByTestId("email-read-view").closest('[role="dialog"]')
    ).toBeNull();
  });

  it("unit-2: getEmail failure shows empty state", async () => {
    mockGetEmail.mockRejectedValue(new ApiError(404, "Not found"));

    render(<EmailDetailPage />);

    expect(
      await screen.findByText("E-mail não encontrado")
    ).toBeInTheDocument();
    expect(screen.queryByTitle("Corpo do e-mail")).not.toBeInTheDocument();
    expect(screen.queryByText("corpo visível")).not.toBeInTheDocument();
  });

  it("unit-3: Back listHref includes folder account q", async () => {
    mockSearch = "folder=Sent&account=acc-1&q=hello";
    mockGetEmail.mockResolvedValue(sampleEmail());

    render(<EmailDetailPage />);

    const back = await screen.findByRole("link", {
      name: "Voltar à caixa de entrada",
    });
    const href = back.getAttribute("href") ?? "";
    const params = new URL(href, "http://localhost").searchParams;
    expect(params.get("folder")).toBe("Sent");
    expect(params.get("account")).toBe("acc-1");
    expect(params.get("q")).toBe("hello");
  });
});
