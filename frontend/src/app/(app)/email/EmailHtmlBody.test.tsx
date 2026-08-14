import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import { EmailHtmlBody } from "./EmailHtmlBody";

function iframeSrcDoc(): string {
  const iframe = screen.getByTitle("Corpo do e-mail");
  return iframe.getAttribute("srcDoc") ?? iframe.getAttribute("srcdoc") ?? "";
}

describe("EmailHtmlBody (melhorar-visualizacao-de-emails-task-htmlbody-1)", () => {
  it("unit-1: srcDoc contains provided HTML and has no prose class", () => {
    const { container } = render(<EmailHtmlBody html="<p>Hi there</p>" />);

    const iframe = screen.getByTitle("Corpo do e-mail");
    expect(iframe.tagName).toBe("IFRAME");
    expect(iframeSrcDoc()).toContain("Hi there");
    expect(iframe.className).not.toMatch(/\bprose\b/);
    expect(container.querySelector(".prose")).toBeNull();
  });

  it("unit-2: sandbox forbids scripts", () => {
    render(<EmailHtmlBody html="<p>Hi there</p>" />);

    const iframe = screen.getByTitle("Corpo do e-mail");
    const sandbox = iframe.getAttribute("sandbox") ?? "";
    expect(sandbox).toBe("allow-popups allow-popups-to-escape-sandbox");
    expect(sandbox).not.toContain("allow-scripts");
    expect(sandbox).not.toContain("allow-same-origin");
  });

  it("unit-3: light reading canvas in srcDoc", () => {
    render(<EmailHtmlBody html="<p>Hi there</p>" />);

    expect(iframeSrcDoc().replace(/\s/g, "")).toMatch(/background:#fff/);
  });

  it("unit-4: images constrained and body overflow auto", () => {
    render(<EmailHtmlBody html="<p>Hi there</p>" />);

    const compact = iframeSrcDoc().replace(/\s/g, "");
    expect(compact).toMatch(/img\{max-width:100%/);
    expect(compact).toMatch(/body\{[^}]*overflow:auto/);
  });

  it("unit-5: srcDoc passes through inline style without a second strip", () => {
    render(
      <EmailHtmlBody html={'<p style="color:red">Hello</p>'} />
    );

    expect(iframeSrcDoc()).toContain('style="color:red"');
  });

  it("unit-6: wrapper CSS drops table max-width, keeps img constraint and light canvas", () => {
    render(<EmailHtmlBody html="<p>Hi there</p>" />);

    const compact = iframeSrcDoc().replace(/\s/g, "");
    expect(compact).toMatch(/img\{max-width:100%/);
    expect(compact).toMatch(/body\{[^}]*overflow:auto/);
    expect(compact).toMatch(/background:#fff/);
    expect(compact).not.toMatch(/table\{max-width:100%/);

    const sandbox = screen.getByTitle("Corpo do e-mail").getAttribute("sandbox") ?? "";
    expect(sandbox).not.toContain("allow-scripts");
  });
});
