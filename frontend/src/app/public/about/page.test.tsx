import { readFileSync } from "node:fs";
import path from "node:path";
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

import AboutPage from "./page";

describe("AboutPage — Google OAuth homepage purpose", () => {
  it("is not a login form", () => {
    render(<AboutPage />);
    expect(screen.queryByRole("form")).not.toBeInTheDocument();
  });

  it('shows the app name "Jeff AI" as the main heading', () => {
    render(<AboutPage />);
    expect(
      screen.getByRole("heading", { level: 1, name: "Jeff AI" })
    ).toBeInTheDocument();
  });

  it("explains the app purpose in English above any sign-in link", () => {
    render(<AboutPage />);
    expect(document.body.textContent).toMatch(
      /self-hosted artificial intelligence assistant/i
    );
    expect(document.body.textContent).toMatch(
      /Why Jeff AI requests Google user data/
    );
    expect(document.body.textContent).toMatch(
      /synchronize incoming email and to send messages/
    );
  });

  it("explains the app purpose in Portuguese", () => {
    render(<AboutPage />);
    expect(document.body.textContent).toMatch(/auto-hospedado/);
    expect(document.body.textContent).toMatch(
      /Por que o Jeff AI solicita dados da sua conta Google/
    );
  });

  it("exposes an English Privacy Policy link matching /public/privacy", () => {
    render(<AboutPage />);
    const links = screen.getAllByRole("link", { name: "Privacy Policy" });
    expect(links.length).toBeGreaterThan(0);
    for (const link of links) {
      expect(link).toHaveAttribute("href", "/public/privacy");
    }
  });

  it("exposes a Portuguese privacy policy link matching /public/privacy", () => {
    render(<AboutPage />);
    const links = screen.getAllByRole("link", {
      name: /política de privacidade/i,
    });
    expect(links.length).toBeGreaterThan(0);
    for (const link of links) {
      expect(link).toHaveAttribute("href", "/public/privacy");
    }
  });

  it('sets logo alt to "Jeff AI"', () => {
    render(<AboutPage />);
    expect(screen.getByRole("img", { name: "Jeff AI" })).toBeInTheDocument();
  });
});

describe("AboutPage metadata — Google brand crawler tags", () => {
  it("exports applicationName and openGraph.siteName as Jeff AI", () => {
    const source = readFileSync(path.resolve(__dirname, "./page.tsx"), "utf8");
    expect(source).toMatch(/const APP_NAME = "Jeff AI"/);
    expect(source).toMatch(/applicationName:\s*APP_NAME/);
    expect(source).toMatch(/siteName:\s*APP_NAME/);
  });
});
