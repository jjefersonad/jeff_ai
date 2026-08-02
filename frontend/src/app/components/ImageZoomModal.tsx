"use client";

/**
 * Lightbox modal for full-size image inspection.
 *
 * Rendered via `MarkdownContent` and `MermaidDiagram` so the user can click any
 * image embedded in a chat message and view it at full viewport size. Uses
 * shadcn/ui's `Dialog` (Radix under the hood) for built-in ESC-to-close,
 * focus trapping, and scroll lock — no custom handlers required.
 *
 * The modal renders an `<img>` (not a `<picture>`/`<video>`/iframe) — that's
 * enough for the three in-app image sources today:
 *
 * - `/api/images/<ts>.png` (Gemini-generated PNGs via `AuthenticatedImage`,
 *   which provides a blob URL)
 * - `/api/files/<kind>/<file>.html` (architecture-diagram skill, an HTML
 *   page with inline SVG; treated as an image because the user perceives
 *   it as one)
 * - data: URLs (Mermaid SVG, encoded as `data:image/svg+xml;base64,...`)
 *
 * For other image sources (PDF, video, audio) this would need to dispatch
 * to a different viewer — deferred until a real use case surfaces.
 */

import React from "react";

import {
  Dialog,
  DialogContent,
  DialogTitle,
} from "@/components/ui/dialog";

interface ImageZoomModalProps {
  /**
   * Full URL (or data: URL) of the image to display. Pass `null` when no
   * image is selected — the modal is closed and nothing renders.
   */
  src: string | null;

  /** Alt text for accessibility — also shown as a caption if non-empty. */
  alt: string;

  /**
   * Called when the user dismisses the modal (ESC, click outside, or
   * close button). The parent should clear its `src` state to null.
   */
  onOpenChange: (open: boolean) => void;
}

export function ImageZoomModal({ src, alt, onOpenChange }: ImageZoomModalProps) {
  return (
    <Dialog open={src !== null} onOpenChange={onOpenChange}>
      {/*
        DialogContent uses Radix's built-in overlay + portal. ESC handling,
        focus trap, and body scroll lock are automatic.

        We force `max-w-none` to let the image use the full viewport width
        (Radix's default `sm:max-w-lg` would cap us at 32rem). The
        `bg-transparent` lets our image sit on the overlay's dark backdrop
        without an extra opaque frame.
      */}
      <DialogContent
        className="max-w-none bg-transparent border-none shadow-none p-0"
        onClick={(e) => {
          // Click on the backdrop (outside the image) closes the modal.
          // Click on the image itself does NOT close — prevents accidental
          // dismissal when zooming in.
          if (e.target === e.currentTarget) {
            onOpenChange(false);
          }
        }}
      >
        {/*
          DialogTitle is required for accessibility (Radix warns on
          missing title for screen readers). Hidden visually since the
          modal is purely visual.
        */}
        <DialogTitle className="sr-only">{alt || "Imagem ampliada"}</DialogTitle>

        {src && (
          <img
            src={src}
            alt={alt}
            className="max-w-[90vw] max-h-[90vh] object-contain rounded shadow-2xl"
          />
        )}
      </DialogContent>
    </Dialog>
  );
}