"use client";

import React from "react";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";

interface MermaidDiagramProps {
  code: string;
  isStreaming: boolean;
  /**
   * Fired when the user clicks the rendered diagram. Receives a data URL
   * containing the full SVG so the parent can open a lightbox without
   * refetching or generating a second render pass. Only fires when the
   * diagram has rendered successfully (no error, not streaming).
   */
  onImageClick?: (src: string, alt: string) => void;
}

let mermaidRenderCount = 0;

/**
 * Strips the inline `style="max-width: Npx"` Mermaid always adds to the root
 * `<svg>` (sized to the diagram's natural content width). Left in place, an
 * inline style always wins over the `w-full` Tailwind class below, so small
 * diagrams (a 2-node flowchart, say) render tiny regardless of how much
 * width the chat column actually has available.
 *
 * Returns the original markup unchanged if the SVG fails to parse — the
 * browser's XML parser embeds a `<parsererror>` element in the document on
 * malformed input, and serialising that wrapper pollutes the output with
 * the error message + truncated SVG. Better to return as-is and let
 * `dangerouslySetInnerHTML` surface the parser error to the user than to
 * splice a hybrid error/document string into the chat.
 */
function removeMaxWidthCap(svgMarkup: string): string {
  const doc = new DOMParser().parseFromString(svgMarkup, "image/svg+xml");
  // `<parsererror>` appears as the documentElement when the input is malformed;
  // bail rather than return a wrapper containing the error message.
  const parserError = doc.getElementsByTagName("parsererror")[0];
  if (parserError) {
    return svgMarkup;
  }
  const svgEl = doc.documentElement;
  svgEl.removeAttribute("style");
  return new XMLSerializer().serializeToString(svgEl);
}

/**
 * Normalizes `<br>` to XML-compliant `<br/>` in an SVG string.
 *
 * Mermaid generates `<br>` without self-close, which is valid in HTML but not
 * in XML/SVG (where `<br>` must be `<br/>`). When the SVG is embedded inline
 * via `dangerouslySetInnerHTML`, the browser's XML/HTML parser fails with
 * "Opening and ending tag mismatch: br line 1 and p" if a `<br>` ends up
 * inside a `<p>` within a `<foreignObject>`. Converting `<br>` → `<br/>`
 * guarantees the output is well-formed XML.
 */
function normalizeVoidElements(svgMarkup: string): string {
  // Match `<br>` only when NOT followed by `</br>` — i.e. the bare void form
  // that is valid in HTML but invalid in XML/SVG.  Does not touch `<br/>` or
  // `<br></br>` (explicit close tag).
  return svgMarkup.replace(/<br\s*(?:\/\s*)?>(?!<\/br>)/gi, "<br/>");
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
export function MermaidDiagram({ code, isStreaming, onImageClick }: MermaidDiagramProps) {
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
        const normalized = normalizeVoidElements(resized);

        if (!cancelled) {
          setSvg(normalized);
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
    // the inline max-width cap stripped so it can fill the container width,
    // and `<br>` normalized to `<br/>` so the SVG is well-formed XML.
    <div
      className="my-2 max-w-full overflow-x-auto [&_svg]:w-full [&_svg]:h-auto cursor-pointer"
      role="button"
      tabIndex={0}
      onClick={() => {
        if (!svg) return;
        // Encode the SVG as a data URL so the lightbox can render it
        // without needing a blob URL roundtrip or re-encoding.
        const dataUrl = `data:image/svg+xml;base64,${btoa(
          unescape(encodeURIComponent(svg))
        )}`;
        onImageClick?.(dataUrl, "Mermaid diagram");
      }}
      onKeyDown={(e) => {
        if ((e.key === "Enter" || e.key === " ") && svg) {
          e.preventDefault();
          const dataUrl = `data:image/svg+xml;base64,${btoa(
            unescape(encodeURIComponent(svg))
          )}`;
          onImageClick?.(dataUrl, "Mermaid diagram");
        }
      }}
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  );
}
