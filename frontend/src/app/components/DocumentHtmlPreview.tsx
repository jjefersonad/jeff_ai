"use client";

/**
 * Embedded preview for generated HTML documents (`/api/files/html/*.html`).
 *
 * Loads via authenticated fetch + blob URL (same pattern as AuthenticatedImage)
 * so the session cookie works across the frontend/API split. Renders an iframe
 * — never an `<img>` / ImageZoomModal — and always keeps a fallback link.
 */

import React from "react";

import { cn } from "@/lib/utils";
import { DownloadError, fetchAuthenticatedBlobUrl } from "@/lib/api";

export function isHtmlDocumentUrl(url: string): boolean {
  try {
    const path = new URL(url, "http://local.invalid").pathname;
    return /\/api\/files\/html\/[^/]+\.html$/i.test(path);
  } catch {
    return false;
  }
}

interface DocumentHtmlPreviewProps {
  url: string;
  /** Optional label for the fallback link. */
  title?: string;
  className?: string;
}

export function DocumentHtmlPreview({
  url,
  title,
  className,
}: DocumentHtmlPreviewProps) {
  const [objectUrl, setObjectUrl] = React.useState<string | null>(null);
  const [errorMessage, setErrorMessage] = React.useState<string | null>(null);

  React.useEffect(() => {
    let cancelled = false;
    let createdUrl: string | undefined;

    setObjectUrl(null);
    setErrorMessage(null);

    fetchAuthenticatedBlobUrl(url)
      .then((blobUrl) => {
        if (cancelled) {
          URL.revokeObjectURL(blobUrl);
          return;
        }
        createdUrl = blobUrl;
        setObjectUrl(blobUrl);
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        const message =
          error instanceof DownloadError && error.kind === "unauthorized"
            ? "Sessão expirada. Faça login novamente para ver o preview."
            : "Não foi possível carregar o preview HTML.";
        setErrorMessage(message);
      });

    return () => {
      cancelled = true;
      if (createdUrl) URL.revokeObjectURL(createdUrl);
    };
  }, [url]);

  const linkLabel = title?.trim() || "Abrir preview HTML";

  return (
    <div
      className={cn(
        "my-3 flex w-full max-w-full flex-col gap-2 overflow-hidden rounded-md border border-border bg-surface",
        className
      )}
      data-testid="document-html-preview"
    >
      {objectUrl ? (
        <iframe
          title="Preview HTML"
          src={objectUrl}
          sandbox="allow-same-origin"
          className="h-[min(70vh,640px)] w-full border-0 bg-white"
        />
      ) : errorMessage ? (
        <p className="px-3 py-2 text-xs text-destructive">{errorMessage}</p>
      ) : (
        <p className="px-3 py-2 text-xs text-muted-foreground">
          Carregando preview…
        </p>
      )}
      <div className="flex items-center justify-between gap-2 border-t border-border px-3 py-2">
        <a
          href={url}
          target="_blank"
          rel="noopener noreferrer"
          className="text-primary text-sm no-underline hover:underline"
        >
          {linkLabel}
        </a>
      </div>
    </div>
  );
}
