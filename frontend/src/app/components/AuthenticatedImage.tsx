"use client";

import React from "react";
import { cn } from "@/lib/utils";
import { DownloadError, fetchAuthenticatedBlobUrl } from "@/lib/api";

interface AuthenticatedImageProps {
  src: string;
  alt?: string;
  className?: string;
  /**
   * While the parent markdown message is still streaming, skip fetch until the
   * URL looks complete (has an image extension). Avoids a cascade of failed
   * loads / "[Imagem não carregada]" fallbacks as tokens arrive.
   */
  isStreaming?: boolean;
  loading?: "lazy" | "eager";
  onLoad?: () => void;
  onClick?: () => void;
}

function isCompleteImageUrl(url: string): boolean {
  try {
    const path = new URL(url, "http://local.invalid").pathname;
    return /\.(png|jpe?g|gif|webp|bmp)$/i.test(path);
  } catch {
    return false;
  }
}

/**
 * Loads a session-protected image (`/api/images/...`, `/api/references/...`)
 * via authenticated fetch + blob URL. Native `<img src>` cannot reliably carry
 * the Jeff AI session cookie across the frontend/API origin split.
 */
export function AuthenticatedImage({
  src,
  alt = "",
  className,
  isStreaming = false,
  loading = "lazy",
  onLoad,
  onClick,
}: AuthenticatedImageProps) {
  const [objectUrl, setObjectUrl] = React.useState<string | null>(null);
  const [errorMessage, setErrorMessage] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (isStreaming && !isCompleteImageUrl(src)) {
      setObjectUrl(null);
      setErrorMessage(null);
      return;
    }

    let cancelled = false;
    let createdUrl: string | undefined;

    setObjectUrl(null);
    setErrorMessage(null);

    fetchAuthenticatedBlobUrl(src)
      .then((url) => {
        if (cancelled) {
          URL.revokeObjectURL(url);
          return;
        }
        createdUrl = url;
        setObjectUrl(url);
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        const message =
          error instanceof DownloadError && error.kind === "unauthorized"
            ? "Sessão expirada. Faça login novamente para ver a imagem."
            : alt
              ? `[Imagem não carregada: ${alt}]`
              : "[Imagem não carregada]";
        setErrorMessage(message);
      });

    return () => {
      cancelled = true;
      if (createdUrl) URL.revokeObjectURL(createdUrl);
    };
  }, [src, alt, isStreaming]);

  // Use <span> (phrasing content), never <div>: this component is rendered
  // from markdown's `img` override inside `<p>`, and a block descendant there
  // triggers a React hydration error.
  if (errorMessage) {
    return (
      <span className="block text-muted-foreground text-sm p-4 border border-dashed border-border rounded-lg">
        {errorMessage}
      </span>
    );
  }

  if (!objectUrl) {
    return (
      <span
        className={cn(
          "block min-h-24 animate-pulse rounded-lg bg-muted",
          className
        )}
        aria-busy="true"
        aria-label={alt || "Carregando imagem"}
      />
    );
  }

  return (
    <img
      src={objectUrl}
      alt={alt}
      className={className}
      loading={loading}
      onLoad={onLoad}
      onClick={onClick}
    />
  );
}
