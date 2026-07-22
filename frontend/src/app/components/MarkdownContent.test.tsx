import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
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
