import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

/**
 * Static OAuth brand-verification homepage. Google's checker caches a
 * verdict per URL and often fails Next.js/React HTML; this file is plain
 * HTML with no logo, served from `frontend/public/jeff-ai.html`.
 */
describe("jeff-ai.html — Google OAuth brand homepage", () => {
  const html = readFileSync(
    path.resolve(__dirname, "../../../public/jeff-ai.html"),
    "utf8"
  );

  it("uses Jeff AI as title and h1", () => {
    expect(html).toMatch(/<title>Jeff AI<\/title>/);
    expect(html).toMatch(/<h1>Jeff AI<\/h1>/);
  });

  it("explains the app purpose and why it requests Google user data", () => {
    expect(html).toMatch(/self-hosted artificial intelligence assistant/);
    expect(html).toMatch(/Why Jeff AI requests Google user data/);
    expect(html).toMatch(/synchronize incoming email and to send messages/);
  });

  it("links the exact privacy and terms URLs used on the OAuth consent screen", () => {
    expect(html).toContain(
      'href="https://jeff.conexaoelite.com.br/public/privacy"'
    );
    expect(html).toContain(
      'href="https://jeff.conexaoelite.com.br/public/terms"'
    );
    expect(html).toContain(">Privacy Policy<");
  });

  it("does not include the Conexão Elite logo, which would mismatch the Jeff AI app name", () => {
    expect(html).not.toMatch(/logo-conexao-elite/i);
    expect(html).not.toMatch(/<img/i);
  });
});
