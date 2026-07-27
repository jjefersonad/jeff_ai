import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { ApiError, setUnauthorizedHandler } from "./api";
import { buildUsagePath, fetchUsage } from "./usage";

describe("buildUsagePath", () => {
  it("omits empty filters", () => {
    expect(buildUsagePath()).toBe("/api/usage");
  });

  it("includes from/to query params for period filter (REQ-002)", () => {
    expect(
      buildUsagePath({ from: "2026-07-01T00:00:00", to: "2026-07-25T23:59:59" })
    ).toBe(
      "/api/usage?from=2026-07-01T00%3A00%3A00&to=2026-07-25T23%3A59%3A59"
    );
  });
});

describe("fetchUsage", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    process.env.NEXT_PUBLIC_API_URL = "http://backend.test";
  });

  afterEach(() => {
    global.fetch = originalFetch;
    setUnauthorizedHandler(null);
  });

  it("calls GET /api/usage with credentials and returns totals", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          prompt_tokens: 1,
          completion_tokens: 2,
          total_tokens: 3,
          filters: {},
        }),
        { status: 200 }
      )
    );
    global.fetch = fetchMock;

    const result = await fetchUsage({ from: "2026-07-01T00:00:00" });

    expect(result.total_tokens).toBe(3);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toContain("/api/usage?");
    expect(url).toContain("from=");
    expect(init.credentials).toBe("include");
  });

  it("throws ApiError on non-OK response", async () => {
    global.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: "Forbidden" }), { status: 403 })
    );

    await expect(fetchUsage()).rejects.toThrow(ApiError);
  });
});
