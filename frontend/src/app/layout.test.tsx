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

/**
 * google-oauth-verification-brand-fix-task-verification-1 / google-site-verification REQ-001:
 * the root layout's `metadata` export carries title/description and a
 * `verification.google` field sourced from `process.env.GOOGLE_SITE_VERIFICATION`,
 * present only when that env var is set.
 *
 * Note: `layout.tsx` cannot be dynamically imported under vitest — it calls
 * `next/font/google`'s `Inter(...)`, which only works inside Next's own build
 * pipeline ("Inter is not a function" outside it). So, consistent with the
 * `RootLayout — empresario-ux-pt-br REQ-001` suite above, this asserts against
 * the file's source text rather than the evaluated module.
 */
describe("RootLayout metadata — google-site-verification REQ-001", () => {
  const read = (rel: string) =>
    readFileSync(path.resolve(__dirname, rel), "utf8");
  const source = read("./layout.tsx");

  it('exports metadata.title "Jeff AI" and a non-empty description', () => {
    expect(source).toMatch(/title:\s*"Jeff AI"/);
    expect(source).toMatch(/description:\s*"[^"]+"/);
  });

  it("sources verification.google from process.env.GOOGLE_SITE_VERIFICATION (server-only, no NEXT_PUBLIC_ prefix)", () => {
    expect(source).toMatch(/process\.env\.GOOGLE_SITE_VERIFICATION/);
    expect(source).not.toMatch(/NEXT_PUBLIC_GOOGLE_SITE_VERIFICATION/);
  });

  it("only includes verification.google when the env var is truthy, so an unset var can't leak an empty/undefined meta tag", () => {
    // Guards against an unconditional `verification: { google: process.env.GOOGLE_SITE_VERIFICATION }`,
    // which would render `content="undefined"` when the var is unset instead of omitting the tag.
    expect(source).toMatch(/verification:\s*process\.env\.GOOGLE_SITE_VERIFICATION\s*\?/);
  });
});
