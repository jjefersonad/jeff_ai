import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { MermaidDiagram } from "./MermaidDiagram";

const mockInitialize = vi.fn();
const mockRender = vi.fn();

vi.mock("mermaid", () => ({
  default: {
    initialize: (...args: unknown[]) => mockInitialize(...args),
    render: (...args: unknown[]) => mockRender(...args),
  },
}));

function mockMatchMedia(matches: boolean) {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches,
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })),
  });
}

const VALID_CODE = "flowchart TD\n  A --> B";

describe("MermaidDiagram", () => {
  beforeEach(() => {
    mockInitialize.mockReset();
    mockRender.mockReset();
    mockMatchMedia(false);
  });

  it("REQ-001: renders mermaid's own sanitized SVG for valid syntax once streaming has finished", async () => {
    mockRender.mockResolvedValue({
      svg: '<svg xmlns="http://www.w3.org/2000/svg" data-testid="diagram-svg"></svg>',
    });

    const { container } = render(
      <MermaidDiagram code={VALID_CODE} isStreaming={false} />
    );

    await waitFor(() => {
      expect(container.querySelector("svg")).toBeTruthy();
    });

    expect(mockRender).toHaveBeenCalled();
  });

  it("sizing fix: strips mermaid's inline max-width cap so the diagram can fill the container width", async () => {
    mockRender.mockResolvedValue({
      svg: '<svg xmlns="http://www.w3.org/2000/svg" width="100%" style="max-width: 200px;" viewBox="0 0 200 100"><text>hi</text></svg>',
    });

    const { container } = render(
      <MermaidDiagram code={VALID_CODE} isStreaming={false} />
    );

    await waitFor(() => {
      expect(container.querySelector("svg")).toBeTruthy();
    });

    const svgEl = container.querySelector("svg");
    expect(svgEl?.getAttribute("style")).toBeNull();
  });

  it("REQ-003: falls back to the code view when mermaid.render throws", async () => {
    mockRender.mockRejectedValue(new Error("invalid mermaid syntax"));

    const { container } = render(
      <MermaidDiagram code="not a real diagram" isStreaming={false} />
    );

    await waitFor(() => {
      expect(container.querySelector("svg")).toBeFalsy();
    });

    expect(screen.getByText(/not a real diagram/)).toBeInTheDocument();
  });

  it("REQ-004: initializes mermaid with the dark theme when the OS prefers dark", async () => {
    mockMatchMedia(true);
    mockRender.mockResolvedValue({ svg: "<svg></svg>" });

    render(<MermaidDiagram code={VALID_CODE} isStreaming={false} />);

    await waitFor(() => {
      expect(mockInitialize).toHaveBeenCalledWith(
        expect.objectContaining({ theme: "dark", securityLevel: "strict" })
      );
    });
  });

  it("REQ-004: initializes mermaid with the default theme when the OS prefers light", async () => {
    mockMatchMedia(false);
    mockRender.mockResolvedValue({ svg: "<svg></svg>" });

    render(<MermaidDiagram code={VALID_CODE} isStreaming={false} />);

    await waitFor(() => {
      expect(mockInitialize).toHaveBeenCalledWith(
        expect.objectContaining({ theme: "default", securityLevel: "strict" })
      );
    });
  });

  it("REQ-002: does not attempt to render while isStreaming is true", async () => {
    const { container } = render(
      <MermaidDiagram code={VALID_CODE} isStreaming={true} />
    );

    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(mockRender).not.toHaveBeenCalled();
    expect(container.querySelector("svg")).toBeFalsy();
    expect(container.textContent).toContain("flowchart");
  });
});

describe("MermaidDiagram - image click handler", () => {
  beforeEach(() => {
    mockInitialize.mockReset();
    mockRender.mockReset();
    mockMatchMedia(false);
  });

  it("calls onImageClick with a data: URL when the diagram wrapper is clicked", async () => {
    const onImageClick = vi.fn();
    const user = userEvent.setup();

    mockRender.mockResolvedValue({
      svg: '<svg xmlns="http://www.w3.org/2000/svg" data-testid="diagram-svg"></svg>',
    });

    const { container } = render(
      <MermaidDiagram
        code={VALID_CODE}
        isStreaming={false}
        onImageClick={onImageClick}
      />
    );

    // Wait for the diagram to render (mermaid.render resolves async)
    await waitFor(() => {
      expect(container.querySelector("svg")).toBeTruthy();
    });

    // Find the clickable wrapper (it has role="button" + cursor-pointer)
    const wrapper = container.querySelector("[role='button']");
    expect(wrapper).toBeTruthy();

    await user.click(wrapper as HTMLElement);

    expect(onImageClick).toHaveBeenCalledTimes(1);
    const [src, alt] = onImageClick.mock.calls[0];
    expect(src).toMatch(/^data:image\/svg\+xml;base64,/);
    expect(alt).toBe("Mermaid diagram");
  });

  it("does not call onImageClick before the diagram has rendered", async () => {
    const onImageClick = vi.fn();

    const { container } = render(
      <MermaidDiagram
        code={VALID_CODE}
        isStreaming={false}
        onImageClick={onImageClick}
      />
    );

    // Diagram not yet rendered — wrapper shows the code-fallback.
    expect(container.querySelector("svg")).toBeFalsy();
    expect(onImageClick).not.toHaveBeenCalled();
  });
});
