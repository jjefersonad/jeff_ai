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

vi.mock("next/image", () => ({
  default: ({ src, alt, ...rest }: { src: string; alt: string }) => (
    <img
      src={src}
      alt={alt}
      {...rest}
    />
  ),
}));

import LandingPage from "./page";

describe("LandingPage — public-marketing-landing-page REQ-002", () => {
  it("renders visible descriptive text explaining Jeff AI's purpose, independent of any login form", () => {
    render(<LandingPage />);
    expect(screen.queryByRole("form")).not.toBeInTheDocument();
    expect(document.body.textContent).toMatch(/auto-hospedad/i);
    expect(document.body.textContent).toMatch(/assistente/i);
  });
});

describe("LandingPage — public-marketing-landing-page REQ-003", () => {
  it('visibly displays "Jeff AI" exactly, matching the OAuth consent screen app name', () => {
    render(<LandingPage />);
    expect(
      screen.getByRole("heading", { name: "Jeff AI" })
    ).toBeInTheDocument();
  });
});

describe("LandingPage — app-branding-consistency REQ-002", () => {
  it('shows the same app name "Jeff AI" used on the privacy and terms pages', () => {
    render(<LandingPage />);
    expect(screen.getAllByText("Jeff AI").length).toBeGreaterThan(0);
  });
});

describe("LandingPage — design D2 links", () => {
  it("contains a link to /public/login", () => {
    render(<LandingPage />);
    expect(
      screen.getByRole("link", { name: /entrar/i })
    ).toHaveAttribute("href", "/public/login");
  });

  it("contains a link to /public/privacy", () => {
    render(<LandingPage />);
    const privacyLinks = screen.getAllByRole("link", {
      name: /política de privacidade/i,
    });
    expect(privacyLinks.length).toBeGreaterThan(0);
    for (const link of privacyLinks) {
      expect(link).toHaveAttribute("href", "/public/privacy");
    }
  });

  it("contains a link to /public/terms", () => {
    render(<LandingPage />);
    expect(
      screen.getByRole("link", { name: /termos de serviço/i })
    ).toHaveAttribute("href", "/public/terms");
  });
});
