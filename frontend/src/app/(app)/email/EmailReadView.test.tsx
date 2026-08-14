import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";

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

import { EmailReadView } from "./EmailReadView";
import type { Email } from "@/lib/email";

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

describe("EmailReadView (email-detail-full-page-task-readview-1)", () => {
  it("unit-1: reading layout is full pane not a Dialog", () => {
    render(
      <EmailReadView
        email={sampleEmail()}
        listHref="/email"
      />
    );

    const root = screen.getByTestId("email-read-view");
    expect(root.closest('[role="dialog"]')).toBeNull();
    expect(root.className).toMatch(/h-\[calc\(100vh-4rem\)\]/);
    expect(root.className).toMatch(/\bflex-col\b/);
    expect(root.className).toMatch(/\boverflow-hidden\b/);
    expect(root.className).not.toMatch(/\bsm:max-w-4xl\b/);
  });

  it("unit-2: chrome is shrink-0 and body is min-h-0 flex-1", () => {
    render(
      <EmailReadView
        email={sampleEmail()}
        listHref="/email"
      />
    );

    const chrome = screen.getByTestId("email-read-chrome");
    expect(chrome.className).toMatch(/\bshrink-0\b/);
    const body = screen.getByTestId("email-read-body");
    expect(body.className).toMatch(/\bmin-h-0\b/);
    expect(body.className).toMatch(/\bflex-1\b/);
  });

  it("unit-3: icon action tooltips match aria-label", async () => {
    render(
      <EmailReadView
        email={sampleEmail({ is_read: false })}
        listHref="/email"
      />
    );

    const expectedTooltips = [
      "Marcar como lido",
      "Responder",
      "Encaminhar",
      "Mover para outra pasta",
      "Excluir (mover para lixeira)",
    ];

    for (const name of expectedTooltips) {
      const button = screen.getByRole("button", { name });
      expect(button).toHaveAttribute("aria-label", name);
      await userEvent.hover(button);
      expect(await screen.findByRole("tooltip", { name })).toBeInTheDocument();
    }
  });

  it("unit-4: Back link uses listHref", () => {
    const listHref = "/email?folder=Sent&q=hello";
    render(
      <EmailReadView
        email={sampleEmail()}
        listHref={listHref}
      />
    );

    expect(
      screen.getByRole("link", { name: "Voltar à caixa de entrada" })
    ).toHaveAttribute("href", listHref);
  });

  it("unit-5: error state has no message body", () => {
    render(
      <EmailReadView
        email={sampleEmail({
          body_html: "<p>LEAK_HTML_MARKER</p>",
          body_text: "LEAK_TEXT_MARKER",
        })}
        error
        listHref="/email"
      />
    );

    expect(screen.getByText("E-mail não encontrado")).toBeInTheDocument();
    expect(screen.queryByTitle("Corpo do e-mail")).not.toBeInTheDocument();
    expect(screen.queryByText("LEAK_HTML_MARKER")).not.toBeInTheDocument();
    expect(screen.queryByText("LEAK_TEXT_MARKER")).not.toBeInTheDocument();
  });

  it("unit-6: HTML body renders via EmailHtmlBody srcDoc", () => {
    render(
      <EmailReadView
        email={sampleEmail({ body_html: "<p>HTML_ONLY_MARKER</p>" })}
        listHref="/email"
      />
    );

    const iframe = screen.getByTitle("Corpo do e-mail");
    const srcDoc =
      iframe.getAttribute("srcDoc") ?? iframe.getAttribute("srcdoc") ?? "";
    expect(srcDoc).toContain("HTML_ONLY_MARKER");
  });
});
