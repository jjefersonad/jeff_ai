import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock("@/providers/AuthProvider", () => ({
  useAuth: () => ({
    login: vi.fn(),
    isAuthenticating: false,
  }),
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

import LoginPage from "./page";

describe("LoginPage — public-legal-pages REQ-006", () => {
  it("contains a link to /public/privacy", () => {
    render(<LoginPage />);
    expect(
      screen.getByRole("link", { name: /política de privacidade/i })
    ).toHaveAttribute("href", "/public/privacy");
  });

  it("contains a link to /public/terms", () => {
    render(<LoginPage />);
    expect(
      screen.getByRole("link", { name: /termos de serviço/i })
    ).toHaveAttribute("href", "/public/terms");
  });
});
