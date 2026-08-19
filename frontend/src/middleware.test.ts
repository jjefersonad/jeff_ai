import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it, vi } from "vitest";

vi.mock("next/server", () => ({
  NextRequest: class {},
  NextResponse: {
    next: () => ({}),
    redirect: () => ({}),
    rewrite: () => ({}),
  },
}));

import { config, isPublicPath } from "./middleware";

/**
 * frontend-route-guard REQ-007 (add-privacy-policy-and-terms):
 * `/public/privacy` and `/public/terms` MUST be public under the existing
 * `/public/*` prefix so middleware does not redirect unauthenticated visitors
 * to login. Protected app routes MUST stay gated.
 */
describe("isPublicPath — frontend-route-guard REQ-007", () => {
  it("treats /public/privacy as public", () => {
    expect(isPublicPath("/public/privacy")).toBe(true);
  });

  it("treats /public/terms as public", () => {
    expect(isPublicPath("/public/terms")).toBe(true);
  });

  it("treats /public/about as public", () => {
    expect(isPublicPath("/public/about")).toBe(true);
  });

  it("does not treat a protected app path as public", () => {
    expect(isPublicPath("/email")).toBe(false);
  });
});

/**
 * google-oauth-verification-brand-fix-task-middleware-1 / REQ-001, REQ-004
 * (`public-marketing-landing-page`).
 *
 * The edge-runtime middleware is hard to drive in isolation (it depends on
 * Next.js' `NextRequest`/`NextResponse`), so we assert the SOURCE TEXT of
 * `src/middleware.ts` against the structural rules from design D1. Same
 * pattern as `frontend/src/lib/dockerfile.frontend.test.ts`.
 */
describe("middleware source — google-oauth-verification-brand-fix REQ-001 / REQ-004", () => {
  const middlewarePath = path.resolve(__dirname, "./middleware.ts");
  const source = readFileSync(middlewarePath, "utf8");

  it("contains a branch gated on pathname === \"/\"", () => {
    expect(source).toMatch(/pathname\s*===\s*"\/"/);
  });

  it("that branch also requires the absence of the session cookie", () => {
    // Must be a single conditional of the form
    //   pathname === "/" && !request.cookies.has(SESSION_COOKIE_NAME)
    expect(source).toMatch(
      /pathname\s*===\s*"\/"\s*&&\s*!\s*request\.cookies\.has\(\s*SESSION_COOKIE_NAME\s*\)/,
    );
  });

  it("uses NextResponse.rewrite (not redirect) to /public/landing inside that branch", () => {
    // The rewrite line itself must look like:
    //   NextResponse.rewrite(new URL("/public/landing", request.url))
    // exactly — no indirection, no extra arguments.
    expect(source).toContain(
      'NextResponse.rewrite(new URL("/public/landing", request.url))',
    );
  });

  it("keeps the existing redirect-to-login branch intact", () => {
    expect(source).toMatch(/NextResponse\.redirect\(loginUrl\)/);
  });

  it("keeps the existing isPublicPath() guard intact and called first", () => {
    const publicIdx = source.indexOf("isPublicPath(pathname)");
    const redirectIdx = source.indexOf("NextResponse.redirect(loginUrl)");
    expect(publicIdx).toBeGreaterThanOrEqual(0);
    expect(redirectIdx).toBeGreaterThanOrEqual(0);
    expect(publicIdx).toBeLessThan(redirectIdx);
  });
});

/**
 * The middleware `matcher` decides which requests reach the auth gate at all.
 * Listing single filenames (the original `favicon.ico`) left every other
 * static file gated: an unauthenticated `GET /logo-conexao-elite.png` or
 * `GET /icon.png` answered 307 → `/public/login`, so the landing page's logo
 * and browser-tab icon were invisible to exactly the logged-out audience the
 * page targets.
 */
describe("middleware matcher — static assets are never auth-gated", () => {
  const matcher = new RegExp(`^${config.matcher[0]}$`);

  it.each([
    "/logo-conexao-elite.png",
    "/icon.png",
    "/apple-icon.png",
    "/favicon.ico",
    "/robots.txt",
    "/sitemap.xml",
    "/jeff-ai.html",
    "/next.svg",
    "/fonts/inter.woff2",
  ])("does not run middleware for %s", (pathname) => {
    expect(matcher.test(pathname)).toBe(false);
  });

  it.each(["/_next/static/chunk.js", "/_next/image", "/api/me"])(
    "keeps the pre-existing exclusion for %s",
    (pathname) => {
      expect(matcher.test(pathname)).toBe(false);
    },
  );

  it.each(["/", "/email", "/crm", "/admin/users", "/public/landing", "/public/about"])(
    "still runs middleware for the protected/app route %s",
    (pathname) => {
      expect(matcher.test(pathname)).toBe(true);
    },
  );
});
