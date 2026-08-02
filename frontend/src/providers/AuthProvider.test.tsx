import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";

import { AuthProvider, useAuth } from "./AuthProvider";
import { setUnauthorizedHandler } from "@/lib/api";

const replaceMock = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: replaceMock }),
}));

describe("AuthProvider session rehydration (auth-session-rehydration-task-frontend-auth-1)", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    process.env.NEXT_PUBLIC_API_URL = "http://backend.test";
    replaceMock.mockReset();
  });

  afterEach(() => {
    global.fetch = originalFetch;
    setUnauthorizedHandler(null);
  });

  it("unit-1: rehydrates user on mount when GET /api/me resolves 200 (REQ-006 scenario 1)", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        new Response(JSON.stringify({ username: "alice", role: "admin" }), { status: 200 })
      );
    global.fetch = fetchMock;

    const { result } = renderHook(() => useAuth(), { wrapper: AuthProvider });

    await waitFor(() => {
      expect(result.current.isRehydrating).toBe(false);
    });

    expect(result.current.isAuthenticated).toBe(true);
    expect(result.current.user).toEqual({ username: "alice", role: "admin" });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://backend.test/api/me");
    expect(init.credentials).toBe("include");
  });

  it("unit-2: stays unauthenticated without redirecting when GET /api/me resolves 401 (REQ-006 scenario 2)", async () => {
    global.fetch = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify({ detail: "Unauthorized" }), { status: 401 }));

    const { result } = renderHook(() => useAuth(), { wrapper: AuthProvider });

    await waitFor(() => {
      expect(result.current.isRehydrating).toBe(false);
    });

    expect(result.current.isAuthenticated).toBe(false);
    expect(result.current.user).toBeNull();
    expect(replaceMock).not.toHaveBeenCalled();
  });
});
