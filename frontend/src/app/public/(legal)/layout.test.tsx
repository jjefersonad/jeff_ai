import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
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

import LegalLayout from "./layout";

describe("LegalLayout — add-privacy-policy-and-terms", () => {
  it("does not render the authenticated app shell (REQ-008)", () => {
    render(
      <LegalLayout>
        <p>child content</p>
      </LegalLayout>
    );

    expect(screen.getByText("child content")).toBeInTheDocument();
    expect(screen.queryByTestId("nav-sidebar")).not.toBeInTheDocument();
    expect(screen.queryByTestId("user-menu")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: "JEFF" })
    ).not.toBeInTheDocument();
  });

  it("exposes footer links to privacy, terms, and login (REQ-006)", () => {
    render(
      <LegalLayout>
        <p>child content</p>
      </LegalLayout>
    );

    expect(
      screen.getByRole("link", { name: /política de privacidade/i })
    ).toHaveAttribute("href", "/public/privacy");
    expect(
      screen.getByRole("link", { name: /termos de serviço/i })
    ).toHaveAttribute("href", "/public/terms");
    expect(
      screen.getByRole("link", { name: /entrar/i })
    ).toHaveAttribute("href", "/public/login");
  });
});
