import "@testing-library/jest-dom/vitest";

// jsdom lacks these; Radix primitives (Dialog, Select, ScrollArea) call them
// even when a test never triggers the specific interaction that needs them.
if (typeof window !== "undefined") {
  window.ResizeObserver =
    window.ResizeObserver ??
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    };

  Element.prototype.hasPointerCapture ??= () => false;
  Element.prototype.setPointerCapture ??= () => {};
  Element.prototype.releasePointerCapture ??= () => {};
  Element.prototype.scrollIntoView ??= () => {};
}
