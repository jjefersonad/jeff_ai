import { readFileSync } from "node:fs";
import path from "node:path";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

const mockLogin = vi.fn();
let mockIsAuthenticating = false;

vi.mock("@/providers/AuthProvider", () => ({
  useAuth: () => ({
    login: mockLogin,
    isAuthenticating: mockIsAuthenticating,
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

describe("LoginPage — empresario-ux-pt-br REQ-002", () => {
  beforeEach(() => {
    mockIsAuthenticating = false;
    mockLogin.mockReset();
  });

  it("shows Entrar, Usuário and Senha instead of Sign in / Username / Password", () => {
    render(<LoginPage />);

    expect(screen.getByRole("heading", { name: "Entrar" })).toBeInTheDocument();
    expect(screen.getByLabelText("Usuário")).toBeInTheDocument();
    expect(screen.getByLabelText("Senha")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /entrar/i })).toBeInTheDocument();

    expect(
      screen.queryByRole("heading", { name: "Sign in" })
    ).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Username")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Password")).not.toBeInTheDocument();
    expect(screen.queryByText("Sign in")).not.toBeInTheDocument();
  });

  it("keeps the Portuguese subtitle and legal footer links", () => {
    render(<LoginPage />);
    expect(
      screen.getByText("Use sua conta Jeff AI para continuar.")
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /política de privacidade/i })
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /termos de serviço/i })
    ).toBeInTheDocument();
  });

  it("shows Entrando… while authenticating", () => {
    mockIsAuthenticating = true;
    render(<LoginPage />);
    expect(screen.getByRole("button", { name: /entrando/i })).toBeInTheDocument();
    expect(screen.queryByText(/signing in/i)).not.toBeInTheDocument();
  });

  it("surfaces Falha no login when the backend omits a detail", async () => {
    const user = userEvent.setup();
    mockLogin.mockResolvedValue({ ok: false });
    render(<LoginPage />);

    await user.type(screen.getByLabelText("Usuário"), "ana");
    await user.type(screen.getByLabelText("Senha"), "secret");
    await user.click(screen.getByRole("button", { name: /entrar/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Falha no login");
  });

  it("uses Carregando… as the Suspense fallback, not Loading…", () => {
    const source = readFileSync(path.resolve(__dirname, "./page.tsx"), "utf8");
    expect(source).toMatch(/Carregando…/);
    expect(source).not.toMatch(/Loading…/);
  });

  it("does not add a next-intl (or equivalent) i18n dependency", () => {
    const pkg = JSON.parse(
      readFileSync(path.resolve(__dirname, "../../../../package.json"), "utf8")
    ) as {
      dependencies?: Record<string, string>;
      devDependencies?: Record<string, string>;
    };
    const deps = { ...pkg.dependencies, ...pkg.devDependencies };
    expect(deps["next-intl"]).toBeUndefined();
    expect(
      Object.keys(deps).filter((name) =>
        /^(next-intl|react-intl|i18next|react-i18next|@lingui\/|typesafe-i18n)$/i.test(
          name
        )
      )
    ).toEqual([]);
  });
});
