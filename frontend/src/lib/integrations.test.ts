import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";

import { ApiError } from "./api";
import { createTelegramLinkCode } from "./integrations";

describe("createTelegramLinkCode (telegram-integration-frontend-registration-task-lib-1 unit-1/2 / REQ-002)", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    process.env.NEXT_PUBLIC_API_URL = "http://backend.test";
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("WHEN backend responds 201 THEN resolves to {code, expires_at} via apiFetch", async () => {
    const payload = { code: "ABC123", expires_at: "2026-08-09T12:00:00Z" };
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify(payload), { status: 201 }));
    global.fetch = fetchMock;

    const result = await createTelegramLinkCode();

    expect(result).toEqual(payload);
    const [url, options] = fetchMock.mock.calls[0];
    expect(String(url)).toContain("/api/integrations/telegram/link-code");
    expect(options).toMatchObject({ method: "POST", credentials: "include" });
  });

  it("WHEN backend responds non-2xx THEN throws ApiError with parsed message", async () => {
    const fetchMock = vi.fn(
      async () =>
        new Response(JSON.stringify({ detail: "Unauthorized" }), { status: 401 })
    );
    global.fetch = fetchMock;

    await expect(createTelegramLinkCode()).rejects.toMatchObject({
      status: 401,
      message: "Unauthorized",
    });
    await expect(createTelegramLinkCode()).rejects.toBeInstanceOf(ApiError);
  });
});
