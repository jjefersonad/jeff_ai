import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import { SWRConfig } from "swr";
import {
  clearThreadsSwrCache,
  isThreadsSwrKey,
  threadsSwrKeyFor,
  useThreads,
} from "./useThreads";

// Each renderHook gets its own cache provider so SWR doesn't serve stale
// data cached under the same key by a previous test in this file.
function renderUseThreads(props: Parameters<typeof useThreads>[0]) {
  return renderHook(() => useThreads(props), {
    wrapper: ({ children }) => (
      <SWRConfig value={{ provider: () => new Map() }}>{children}</SWRConfig>
    ),
  });
}

const mockSearch = vi.fn();
const mockDelete = vi.fn();
let mockAuthUser: { id: string; username: string; role: "admin" | "user" } | null =
  {
    id: "user-u",
    username: "alice",
    role: "user",
  };

vi.mock("@/providers/ClientProvider", () => ({
  useClient: () => ({
    threads: {
      search: (...args: unknown[]) => mockSearch(...args),
      delete: (...args: unknown[]) => mockDelete(...args),
    },
  }),
}));

vi.mock("@/providers/AuthProvider", () => ({
  useAuth: () => ({
    user: mockAuthUser,
    isAuthenticated: mockAuthUser !== null,
    isAuthenticating: false,
    isRehydrating: false,
    login: vi.fn(),
    logout: vi.fn(),
  }),
}));

vi.mock("@/lib/config", () => ({
  getConfig: () => ({ assistantId: "test-assistant" }),
}));

const THREAD_1 = {
  thread_id: "t1",
  updated_at: "2026-01-01T00:00:00.000Z",
  status: "idle",
  values: { messages: [] },
};

describe("useThreads - SWR key isolation (fix-thread-list-user-isolation ui-1)", () => {
  it("unit-1: threadsSwrKeyFor embeds users.id so different users do not share cache", () => {
    const keyA = threadsSwrKeyFor("user-a", 0, 20, "assistant-1");
    const keyB = threadsSwrKeyFor("user-b", 0, 20, "assistant-1");
    expect(keyA.userId).toBe("user-a");
    expect(keyB.userId).toBe("user-b");
    expect(keyA).not.toEqual(keyB);
    expect(isThreadsSwrKey(keyA)).toBe(true);
    expect(threadsSwrKeyFor(null, 0, 20, "assistant-1").userId).toBe("anon");
  });

  it("unit-2: clearThreadsSwrCache drops cached thread pages (login/logout)", async () => {
    const mutate = vi.fn().mockResolvedValue(undefined);
    await clearThreadsSwrCache(mutate);
    expect(mutate).toHaveBeenCalledTimes(1);
    const filter = mutate.mock.calls[0][0] as (key: unknown) => boolean;
    expect(filter(threadsSwrKeyFor("user-a", 0, 20, "x"))).toBe(true);
    expect(filter(["unrelated"])).toBe(false);
    expect(mutate.mock.calls[0][1]).toBeUndefined();
    expect(mutate.mock.calls[0][2]).toMatchObject({ revalidate: false });
  });
});

describe("useThreads - deleteThread", () => {
  beforeEach(() => {
    mockSearch.mockReset();
    mockDelete.mockReset();
    mockAuthUser = {
      id: "user-u",
      username: "alice",
      role: "user",
    };
  });

  it("calls client.threads.delete then revalidates the list so the deleted thread is gone", async () => {
    mockSearch.mockResolvedValueOnce([THREAD_1]);
    const { result } = renderUseThreads({});

    await waitFor(() =>
      expect(result.current.data?.flat()).toEqual([
        expect.objectContaining({ id: "t1" }),
      ])
    );

    mockDelete.mockResolvedValueOnce(undefined);
    mockSearch.mockResolvedValueOnce([]);

    await act(async () => {
      await result.current.deleteThread("t1");
    });

    expect(mockDelete).toHaveBeenCalledWith("t1");
    await waitFor(() => expect(result.current.data?.flat()).toEqual([]));
  });

  it("propagates the error and does not revalidate when the delete request fails", async () => {
    mockSearch.mockResolvedValueOnce([THREAD_1]);
    const { result } = renderUseThreads({});

    await waitFor(() =>
      expect(result.current.data?.flat()).toEqual([
        expect.objectContaining({ id: "t1" }),
      ])
    );

    mockDelete.mockRejectedValueOnce(new Error("boom"));

    await expect(
      act(async () => {
        await result.current.deleteThread("t1");
      })
    ).rejects.toThrow("boom");

    // Give any stray revalidation a chance to fire before asserting it didn't.
    await new Promise((r) => setTimeout(r, 50));
    expect(mockSearch).toHaveBeenCalledTimes(1);
    expect(result.current.data?.flat()).toEqual([
      expect.objectContaining({ id: "t1" }),
    ]);
  });
});
