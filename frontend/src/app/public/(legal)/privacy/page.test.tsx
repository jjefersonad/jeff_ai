import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import PrivacyPage from "./page";

describe("PrivacyPage — public-legal-pages", () => {
  it("renders a visible title identifying Política de Privacidade (REQ-001)", () => {
    render(<PrivacyPage />);
    expect(
      screen.getByRole("heading", { level: 1, name: /política de privacidade/i })
    ).toBeInTheDocument();
  });

  it("renders the required privacy sections (REQ-003)", () => {
    render(<PrivacyPage />);
    expect(
      screen.getByRole("heading", { name: /dados coletados/i })
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: /finalidade/i })
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: /retenção/i })
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: /compartilhamento/i })
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: /direitos.*lgpd/i })
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: /exclusão|revogação/i })
    ).toBeInTheDocument();
  });

  it("discloses Gmail OAuth access, sync/send, and encrypted tokens (REQ-003)", () => {
    render(<PrivacyPage />);
    const article = screen.getByRole("article");
    expect(article.textContent).toMatch(/gmail/i);
    expect(article.textContent).toMatch(/oauth/i);
    expect(article.textContent).toMatch(/sincroniz/i);
    expect(article.textContent).toMatch(/enviar/i);
    expect(article.textContent).toMatch(/token/i);
    expect(article.textContent).toMatch(/criptograf/i);
  });

  it("shows an effective date via a time element (REQ-008)", () => {
    render(<PrivacyPage />);
    const time = document.querySelector("time");
    expect(time).toBeTruthy();
    expect(time).toHaveAttribute("dateTime");
    expect(time?.textContent?.trim().length).toBeGreaterThan(0);
  });

  it("declares Portuguese on the article (REQ-003)", () => {
    render(<PrivacyPage />);
    expect(screen.getByRole("article")).toHaveAttribute("lang", "pt-BR");
  });
});
