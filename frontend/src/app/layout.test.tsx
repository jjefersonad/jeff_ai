import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

/**
 * saas-empresario-br-task-ux-1 / empresario-ux-pt-br REQ-001:
 * the document language is pt-BR at the root layout and does not revert
 * to English on public legal pages.
 */
describe("RootLayout — empresario-ux-pt-br REQ-001", () => {
  const read = (rel: string) =>
    readFileSync(path.resolve(__dirname, rel), "utf8");

  it('declares html lang="pt-BR" and not lang="en"', () => {
    const source = read("./layout.tsx");
    expect(source).toMatch(/<html[\s\S]*?\blang="pt-BR"/);
    expect(source).not.toMatch(/\blang="en"/);
  });

  it("does not revert document language to en on /public/privacy or /public/terms", () => {
    const privacy = read("./public/(legal)/privacy/page.tsx");
    const terms = read("./public/(legal)/terms/page.tsx");
    const legalLayout = read("./public/(legal)/layout.tsx");

    expect(privacy).not.toMatch(/\blang="en"/);
    expect(terms).not.toMatch(/\blang="en"/);
    expect(legalLayout).not.toMatch(/\blang="en"/);
    expect(privacy).toMatch(/\blang="pt-BR"/);
    expect(terms).toMatch(/\blang="pt-BR"/);
  });
});
