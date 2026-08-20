import { describe, it, expect, vi } from "vitest";
import { renderHook } from "@testing-library/react";
import { fireEvent } from "@testing-library/react";

import { useEscToClose } from "./useEscToClose";

describe("useEscToClose (crm-lateral-menu-task-hook-1 unit-1 / REQ-004)", () => {
  it("WHEN enabled=true and Escape is pressed THEN onClose is called exactly once", () => {
    const onClose = vi.fn();
    renderHook(() => useEscToClose(true, onClose));

    fireEvent.keyDown(window, { key: "Escape" });

    expect(onClose).toHaveBeenCalledTimes(1);
  });
});

describe("useEscToClose (crm-lateral-menu-task-hook-1 unit-2 / REQ-004)", () => {
  it("WHEN enabled=false and Escape is pressed THEN onClose is not called", () => {
    const onClose = vi.fn();
    renderHook(() => useEscToClose(false, onClose));

    fireEvent.keyDown(window, { key: "Escape" });

    expect(onClose).not.toHaveBeenCalled();
  });
});
