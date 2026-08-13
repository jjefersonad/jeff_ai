import { describe, expect, it, vi } from "vitest";

vi.mock("next/server", () => ({
  NextRequest: class {},
  NextResponse: {
    next: () => ({}),
    redirect: () => ({}),
  },
}));

import { isPublicPath } from "./middleware";

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

  it("does not treat a protected app path as public", () => {
    expect(isPublicPath("/email")).toBe(false);
  });
});
