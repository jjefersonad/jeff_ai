"use client";

import React from "react";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";

interface MermaidDiagramProps {
  code: string;
  isStreaming: boolean;
}

let mermaidRenderCount = 0;

/**
 * Strips the inline `style="max-width: Npx"` Mermaid always adds to the root
 * `<svg>` (sized to the diagram's natural content width). Left in place, an
 * inline style always wins over the `w-full` Tailwind class below, so small
 * diagrams (a 2-node flowchart, say) render tiny regardless of how much
 * width the chat column actually has available.
 */
function removeMaxWidthCap(svgMarkup: string): string {
  const doc = new DOMParser().parseFromString(svgMarkup, "image/svg+xml");
  const svgEl = doc.documentElement;
  svgEl.removeAttribute("style");
  return new XMLSerializer().serializeToString(svgEl);
}

/**
 * Renders a ```mermaid code block as an inline SVG diagram, client-side only.
 * Falls back to the same syntax-highlighted code view used for any other
 * language while streaming or when `mermaid.render()` fails, so an
 * LLM-generated invalid diagram never breaks the surrounding message.
 *
 * No separate DOMPurify pass here: `mermaid.render()` already sanitizes its
 * own output whenever `securityLevel !== "loose"` (set below to "strict"),
 * using `HTML_INTEGRATION_POINTS: { foreignobject: true }` internally so the
 * HTML labels mermaid renders inside `<foreignObject>` survive sanitization.
 * A second bare `DOMPurify.sanitize(svg)` call without that same option
 * strips all label text wholesale (DOMPurify treats HTML nested in an SVG
 * `foreignObject` as a mutation-XSS vector unless told otherwise) — confirmed
 * empirically while investigating a bug report of diagrams rendering with no
 * text. Re-sanitizing on top of mermaid's own pass added no real defense
 * (same library, and mermaid's config already covers the label-injection
 * risk) while being one misconfiguration away from silently breaking again.
 */
export function MermaidDiagram({ code, isStreaming }: MermaidDiagramProps) {
  const [svg, setSvg] = React.useState<string | null>(null);
  const [hasError, setHasError] = React.useState(false);

  React.useEffect(() => {
    if (isStreaming) {
      setSvg(null);
      setHasError(false);
      return;
    }

    let cancelled = false;

    async function renderDiagram() {
      try {
        const { default: mermaid } = await import("mermaid");

        const prefersDark = window.matchMedia(
          "(prefers-color-scheme: dark)"
        ).matches;

        mermaid.initialize({
          startOnLoad: false,
          securityLevel: "strict",
          theme: prefersDark ? "dark" : "default",
        });

        const id = `mermaid-diagram-${mermaidRenderCount++}`;
        const { svg: rawSvg } = await mermaid.render(id, code);
        const resized = removeMaxWidthCap(rawSvg);

        if (!cancelled) {
          setSvg(resized);
          setHasError(false);
        }
      } catch {
        if (!cancelled) {
          setHasError(true);
        }
      }
    }

    renderDiagram();

    return () => {
      cancelled = true;
    };
  }, [code, isStreaming]);

  if (isStreaming || hasError || svg === null) {
    return (
      <SyntaxHighlighter
        style={oneDark}
        language="mermaid"
        PreTag="div"
        className="max-w-full rounded-md text-sm"
        wrapLines={true}
        wrapLongLines={true}
        lineProps={{
          style: {
            wordBreak: "break-all",
            whiteSpace: "pre-wrap",
            overflowWrap: "break-word",
          },
        }}
        customStyle={{
          margin: 0,
          maxWidth: "100%",
          overflowX: "auto",
          fontSize: "0.875rem",
        }}
      >
        {code}
      </SyntaxHighlighter>
    );
  }

  return (
    // svg is mermaid's own sanitized output (securityLevel: "strict"), with
    // the inline max-width cap stripped so it can fill the container width
    <div
      className="my-2 max-w-full overflow-x-auto [&_svg]:w-full [&_svg]:h-auto"
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  );
}
