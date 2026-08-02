import { describe, it, expect, vi, afterEach } from "vitest";
import { setUnauthorizedHandler } from "@/lib/api";
import { fetchWithUnauthorizedCheck } from "./ClientProvider";

describe("fetchWithUnauthorizedCheck (session-expiry-redirect-to-login, frontend-route-guard REQ-003)", () => {
  const originalFetch = global.fetch;

  afterEach(() => {
    global.fetch = originalFetch;
    setUnauthorizedHandler(null);
  });

  it("passes call arguments through to fetch and returns the response unaltered on success", async () => {
    const payload = { hello: "world" };
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(payload), { status: 200 }));
    global.fetch = fetchMock;
    const unauthorizedSpy = vi.fn();
    setUnauthorizedHandler(unauthorizedSpy);

    const response = await fetchWithUnauthorizedCheck("http://backend.test/threads", { method: "GET" });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledWith("http://backend.test/threads", { method: "GET" });
    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toEqual(payload);
    expect(unauthorizedSpy).not.toHaveBeenCalled();
  });

  it("triggers the unauthorized handler when the backend responds 401", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 401 }));
    global.fetch = fetchMock;
    const unauthorizedSpy = vi.fn();
    setUnauthorizedHandler(unauthorizedSpy);

    const response = await fetchWithUnauthorizedCheck("http://backend.test/threads", { method: "GET" });

    expect(unauthorizedSpy).toHaveBeenCalledTimes(1);
    expect(response.status).toBe(401);
  });
});
