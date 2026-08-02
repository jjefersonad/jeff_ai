import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import { SWRConfig } from "swr";
import { useThreads } from "./useThreads";

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

vi.mock("@/providers/ClientProvider", () => ({
  useClient: () => ({
    threads: {
      search: (...args: unknown[]) => mockSearch(...args),
      delete: (...args: unknown[]) => mockDelete(...args),
    },
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

describe("useThreads - deleteThread", () => {
  beforeEach(() => {
    mockSearch.mockReset();
    mockDelete.mockReset();
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
