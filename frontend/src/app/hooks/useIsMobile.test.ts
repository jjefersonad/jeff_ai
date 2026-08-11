import { describe, it, expect, vi } from "vitest";
import { renderHook, act } from "@testing-library/react";

import { useIsMobile } from "./useIsMobile";

function mockMatchMedia(initialMatches: boolean) {
  let changeHandler: ((event: MediaQueryListEvent) => void) | null = null;
  const mql = {
    matches: initialMatches,
    media: "",
    onchange: null,
    addEventListener: vi.fn((event: string, handler: typeof changeHandler) => {
      if (event === "change") changeHandler = handler;
    }),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  };
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      ...mql,
      media: query,
    })),
  });
  return {
    fireChange: (matches: boolean) => {
      mql.matches = matches;
      changeHandler?.({ matches } as MediaQueryListEvent);
    },
  };
}

describe("useIsMobile (mobile-conversations-drawer-task-hook-1 unit-1 / REQ-002)", () => {
  it("WHEN matchMedia reports a mobile-width match after mount THEN it returns true", async () => {
    mockMatchMedia(true);

    const { result } = renderHook(() => useIsMobile());

    await vi.waitFor(() => {
      expect(result.current).toBe(true);
    });
  });

  it("WHEN matchMedia does not match after mount THEN it returns false", async () => {
    mockMatchMedia(false);

    const { result } = renderHook(() => useIsMobile());

    await vi.waitFor(() => {
      expect(result.current).toBe(false);
    });
  });

  it("WHEN the matchMedia change event fires THEN the returned value updates", async () => {
    const { fireChange } = mockMatchMedia(false);

    const { result } = renderHook(() => useIsMobile());

    await vi.waitFor(() => {
      expect(result.current).toBe(false);
    });

    act(() => {
      fireChange(true);
    });

    expect(result.current).toBe(true);
  });
});
