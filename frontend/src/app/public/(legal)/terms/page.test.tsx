import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import TermsPage from "./page";

describe("TermsPage — public-legal-pages", () => {
  it("renders a visible title identifying Termos de Serviço (REQ-002)", () => {
    render(<TermsPage />);
    expect(
      screen.getByRole("heading", { level: 1, name: /termos de serviço/i })
    ).toBeInTheDocument();
  });

  it("renders the required terms sections (REQ-004)", () => {
    render(<TermsPage />);
    expect(
      screen.getByRole("heading", { name: /descrição do serviço/i })
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: /uso aceitável/i })
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: /limitação de responsabilidade/i })
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: /contas de terceiros/i })
    ).toBeInTheDocument();
  });

  it("shows an effective date via a time element (REQ-008)", () => {
    render(<TermsPage />);
    const time = document.querySelector("time");
    expect(time).toBeTruthy();
    expect(time).toHaveAttribute("dateTime");
    expect(time?.textContent?.trim().length).toBeGreaterThan(0);
  });
});
