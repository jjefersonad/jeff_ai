import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { MarkdownContent } from "./MarkdownContent";

const mockMermaidDiagram = vi.fn(
  (_props: { code: string; isStreaming: boolean }) => (
    <div data-testid="mermaid-diagram-mock" />
  )
);

vi.mock("./MermaidDiagram", () => ({
  MermaidDiagram: (props: { code: string; isStreaming: boolean }) =>
    mockMermaidDiagram(props),
}));

const mockAuthenticatedImage = vi.fn(
  (_props: { src: string; alt?: string; isStreaming?: boolean }) => (
    <div data-testid="authenticated-image-mock" />
  )
);

vi.mock("./AuthenticatedImage", () => ({
  AuthenticatedImage: (props: {
    src: string;
    alt?: string;
    isStreaming?: boolean;
  }) => mockAuthenticatedImage(props),
}));

const MERMAID_CONTENT = "```mermaid\nflowchart TD\n  A --> B\n```";

describe("MarkdownContent - mermaid delegation (melhorar-visualizacao-diagramas delta)", () => {
  beforeEach(() => {
    mockMermaidDiagram.mockClear();
  });

  it("ADDED (markdown-message-rendering delta): delegates a mermaid code block to MermaidDiagram", () => {
    render(<MarkdownContent content={MERMAID_CONTENT} isStreaming={false} />);

    expect(mockMermaidDiagram).toHaveBeenCalledWith(
      expect.objectContaining({ code: expect.stringContaining("flowchart TD") })
    );
    expect(screen.getByTestId("mermaid-diagram-mock")).toBeInTheDocument();
  });

  it("REQ-002 (mermaid-diagram-rendering): forwards isStreaming=true to MermaidDiagram while the message is streaming", () => {
    render(<MarkdownContent content={MERMAID_CONTENT} isStreaming={true} />);

    expect(mockMermaidDiagram).toHaveBeenCalledWith(
      expect.objectContaining({ isStreaming: true })
    );
  });

  it("REQ-002-baseline (markdown-message-rendering): non-mermaid languages still render via the generic syntax-highlighted code view", () => {
    const { container } = render(
      <MarkdownContent content={"```python\nprint('hi')\n```"} />
    );

    expect(mockMermaidDiagram).not.toHaveBeenCalled();
    expect(container.textContent).toContain("print");
  });
});

describe("MarkdownContent - authenticated generated images", () => {
  beforeEach(() => {
    mockAuthenticatedImage.mockClear();
  });

  it("routes /api/images/* through AuthenticatedImage (session cookie)", () => {
    render(
      <MarkdownContent content={"![Cool Bulldog](/api/images/20260725121054.png)"} />
    );

    expect(mockAuthenticatedImage).toHaveBeenCalledWith(
      expect.objectContaining({
        src: "/api/images/20260725121054.png",
        alt: "Cool Bulldog",
      })
    );
    expect(screen.getByTestId("authenticated-image-mock")).toBeInTheDocument();
  });

  it("rewrites hallucinated absolute hosts to /api/images/<file>", () => {
    render(
      <MarkdownContent
        content={
          "![Cool Bulldog Portrait](https://your-frontend.com/api/images/20260725121054.png)"
        }
      />
    );

    expect(mockAuthenticatedImage).toHaveBeenCalledWith(
      expect.objectContaining({
        src: "/api/images/20260725121054.png",
        alt: "Cool Bulldog Portrait",
      })
    );
  });
});

// ---------------------------------------------------------------------------
// Image zoom modal — clicking an image opens ImageZoomModal
// ---------------------------------------------------------------------------

describe("MarkdownContent - image zoom modal", () => {
  it("opens ImageZoomModal when user clicks an authenticated image", async () => {
    const user = userEvent.setup();
    mockAuthenticatedImage.mockImplementation((props: {
      src: string;
      alt?: string;
    }) => (
      <img
        data-testid="auth-img"
        src={props.src}
        alt={props.alt || ""}
        onClick={() => props.onImageClick?.(props.src, props.alt || "")}
      />
    ));

    render(
      <MarkdownContent
        content={"![Portrait](/api/images/20260801120000.png)"}
      />
    );

    // Modal is initially closed
    expect(screen.queryByRole("dialog")).toBeNull();

    // Click the authenticated image — should open the modal
    await user.click(screen.getByTestId("auth-img"));

    // Dialog appears
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toBeInTheDocument();

    // The image inside the dialog has the same src as the auth image
    const dialogImg = dialog.querySelector("img");
    expect(dialogImg).toHaveAttribute(
      "src",
      "/api/images/20260801120000.png"
    );
    expect(dialogImg).toHaveAttribute("alt", "Portrait");
  });

  it("opens ImageZoomModal when user clicks a plain <img> (no auth)", async () => {
    const user = userEvent.setup();

    render(
      <MarkdownContent
        content={"![external](https://example.com/cat.png)"}
      />
    );

    // Modal closed initially
    expect(screen.queryByRole("dialog")).toBeNull();

    // Find the image rendered by react-markdown and click it
    const img = screen.getByRole("img", { name: "external" });
    await user.click(img);

    // Dialog opens
    const dialog = await screen.findByRole("dialog");
    const dialogImg = dialog.querySelector("img");
    expect(dialogImg).toHaveAttribute("src", "https://example.com/cat.png");
  });

  it("closes the modal when close button is clicked", async () => {
    const user = userEvent.setup();
    mockAuthenticatedImage.mockImplementation((props: {
      src: string;
      alt?: string;
    }) => (
      <img
        data-testid="auth-img"
        src={props.src}
        alt={props.alt || ""}
        onClick={() => props.onImageClick?.(props.src, props.alt || "")}
      />
    ));

    render(
      <MarkdownContent content={"![x](/api/images/y.png)"} />
    );

    await user.click(screen.getByTestId("auth-img"));
    await screen.findByRole("dialog");

    await user.click(screen.getByRole("button", { name: /close/i }));

    // Dialog gone after close
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("closes the modal when ESC is pressed", async () => {
    const user = userEvent.setup();
    mockAuthenticatedImage.mockImplementation((props: {
      src: string;
      alt?: string;
    }) => (
      <img
        data-testid="auth-img"
        src={props.src}
        alt={props.alt || ""}
        onClick={() => props.onImageClick?.(props.src, props.alt || "")}
      />
    ));

    render(
      <MarkdownContent content={"![x](/api/images/y.png)"} />
    );

    await user.click(screen.getByTestId("auth-img"));
    await screen.findByRole("dialog");

    await user.keyboard("{Escape}");

    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("does not open the modal on load (only on click)", () => {
    mockAuthenticatedImage.mockImplementation((props: {
      src: string;
      alt?: string;
    }) => (
      <img
        data-testid="auth-img"
        src={props.src}
        alt={props.alt || ""}
        // Note: no onClick that fires onImageClick — just renders.
      />
    ));

    render(
      <MarkdownContent content={"![x](/api/images/y.png)"} />
    );

    expect(screen.queryByRole("dialog")).toBeNull();
  });
});
