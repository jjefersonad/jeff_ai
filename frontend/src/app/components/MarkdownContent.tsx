"use client";

import React from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";
import { cn } from "@/lib/utils";

interface MarkdownContentProps {
  content: string;
  className?: string;
}

/**
 * Converte paths absolutos do filesystem para URLs relativas acessíveis pelo frontend.
 * Ex: /deps/backend/outputs/images/20260705091430.png → /api/images/20260705091430.png
 */
function normalizeImagePaths(markdown: string): string {
  // Regex para capturar markdown images com paths absolutos que contêm "outputs/images/"
  // Captura tanto ![alt](path) quanto <img src="path" ...>
  return markdown
    .replace(
      /!\[([^\]]*)\]\(([^)]+\/(?:backend\/)?outputs\/images\/([^/)]+\.png))\)/gi,
      (_match, alt, _fullPath, filename) => {
        return `![${alt}](/api/images/${filename})`;
      }
    )
    .replace(
      /<img[^>]*src=["']([^"']+\/(?:backend\/)?outputs\/images\/([^"/]+\.png))["'][^>]*>/gi,
      (_match, _fullPath, filename) => {
        return `<img src="/api/images/${filename}" />`;
      }
    );
}

/**
 * Converte paths absolutos de documentos Office para a URL servida pelo backend.
 * Defensivo: as tools já devolvem `/api/files/<kind>/<name>`, mas se o path
 * absoluto (`.../outputs/documents/docx/arquivo.docx`) vazar para o markdown,
 * normaliza para o link de download acessível pelo frontend.
 * Ex: /deps/backend/outputs/documents/docx/2026....docx → /api/files/docx/2026....docx
 */
function normalizeDocumentPaths(markdown: string): string {
  return markdown.replace(
    /\[([^\]]*)\]\(([^)]*\/(?:backend\/)?outputs\/documents\/(docx|xlsx|pptx)\/([^/)]+\.(?:docx|xlsx|pptx)))\)/gi,
    (_match, label, _fullPath, kind, filename) => {
      return `[${label}](/api/files/${kind}/${filename})`;
    }
  );
}

/** Rótulo curto exibido no chip de download por tipo de documento. */
const DOCUMENT_LABELS: Record<string, string> = {
  docx: "Word",
  xlsx: "Excel",
  pptx: "PowerPoint",
};

export const MarkdownContent = React.memo<MarkdownContentProps>(
  ({ content, className = "" }) => {
    // Normaliza paths de imagem e de documentos antes de renderizar
    const normalizedContent = normalizeDocumentPaths(normalizeImagePaths(content));

    return (
      <div
        className={cn(
          "prose min-w-0 max-w-full overflow-hidden break-words text-sm leading-relaxed text-inherit [&_h1:first-child]:mt-0 [&_h1]:mb-4 [&_h1]:mt-6 [&_h1]:font-semibold [&_h2:first-child]:mt-0 [&_h2]:mb-4 [&_h2]:mt-6 [&_h2]:font-semibold [&_h3:first-child]:mt-0 [&_h3]:mb-4 [&_h3]:mt-6 [&_h3]:font-semibold [&_h4:first-child]:mt-0 [&_h4]:mb-4 [&_h4]:mt-6 [&_h4]:font-semibold [&_h5:first-child]:mt-0 [&_h5]:mb-4 [&_h5]:mt-6 [&_h5]:font-semibold [&_h6:first-child]:mt-0 [&_h6]:mb-4 [&_h6]:mt-6 [&_h6]:font-semibold [&_p:last-child]:mb-0 [&_p]:mb-4",
          className
        )}
      >
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={{
            code({
              inline,
              className,
              children,
              ...props
            }: {
              inline?: boolean;
              className?: string;
              children?: React.ReactNode;
            }) {
              const match = /language-(\w+)/.exec(className || "");
              return !inline && match ? (
                <SyntaxHighlighter
                  style={oneDark}
                  language={match[1]}
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
                  {String(children).replace(/\n$/, "")}
                </SyntaxHighlighter>
              ) : (
                <code
                  className="bg-surface rounded-sm px-1 py-0.5 font-mono text-[0.9em]"
                  {...props}
                >
                  {children}
                </code>
              );
            },
            pre({ children }: { children?: React.ReactNode }) {
              return (
                <div className="my-4 max-w-full overflow-hidden last:mb-0">
                  {children}
                </div>
              );
            },
            a({
              href,
              children,
            }: {
              href?: string;
              children?: React.ReactNode;
            }) {
              // Documentos Office gerados: renderiza um chip de download.
              const docMatch = href?.match(/\/api\/files\/(docx|xlsx|pptx)\//);
              if (docMatch) {
                const kind = docMatch[1];
                return (
                  <a
                    href={href}
                    download
                    className="my-1 inline-flex items-center gap-2 rounded-md border border-border bg-surface px-3 py-2 text-primary no-underline transition-colors hover:bg-border/40"
                  >
                    <svg
                      xmlns="http://www.w3.org/2000/svg"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      className="h-4 w-4 shrink-0 opacity-70"
                      aria-hidden="true"
                    >
                      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                      <polyline points="7 10 12 15 17 10" />
                      <line x1="12" y1="15" x2="12" y2="3" />
                    </svg>
                    <span className="min-w-0 break-words">{children}</span>
                    <span className="shrink-0 rounded bg-border/50 px-1.5 py-0.5 text-xs font-medium uppercase text-muted-foreground">
                      {DOCUMENT_LABELS[kind] ?? kind}
                    </span>
                  </a>
                );
              }
              return (
                <a
                  href={href}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-primary no-underline hover:underline"
                >
                  {children}
                </a>
              );
            },
            blockquote({ children }: { children?: React.ReactNode }) {
              return (
                <blockquote className="text-primary/50 my-4 border-l-4 border-border pl-4 italic">
                  {children}
                </blockquote>
              );
            },
            ul({ children }: { children?: React.ReactNode }) {
              return (
                <ul className="my-4 pl-6 [&>li:last-child]:mb-0 [&>li]:mb-1">
                  {children}
                </ul>
              );
            },
            ol({ children }: { children?: React.ReactNode }) {
              return (
                <ol className="my-4 pl-6 [&>li:last-child]:mb-0 [&>li]:mb-1">
                  {children}
                </ol>
              );
            },
            img({
              src,
              alt,
            }: {
              src?: string;
              alt?: string;
            }) {
              const isGeneratedImage = src?.startsWith("/api/images/");
              return (
                <img
                  src={src}
                  alt={alt || ""}
                  className={cn(
                    "max-w-full rounded-lg",
                    isGeneratedImage && "shadow-md hover:shadow-lg transition-shadow duration-200 cursor-pointer"
                  )}
                  loading="lazy"
                  onError={(e) => {
                    const target = e.target as HTMLImageElement;
                    target.style.display = "none";
                    const fallback = document.createElement("div");
                    fallback.className = "text-muted-foreground text-sm p-4 border border-dashed border-border rounded-lg";
                    fallback.textContent = alt ? `[Imagem não carregada: ${alt}]` : "[Imagem não carregada]";
                    target.parentNode?.appendChild(fallback);
                  }}
                />
              );
            },
            table({ children }: { children?: React.ReactNode }) {
              return (
                <div className="my-4 overflow-x-auto">
                  <table className="[&_th]:bg-surface w-full border-collapse [&_td]:border [&_td]:border-border [&_td]:p-2 [&_th]:border [&_th]:border-border [&_th]:p-2 [&_th]:text-left [&_th]:font-semibold">
                    {children}
                  </table>
                </div>
              );
            },
          }}
        >
          {normalizedContent}
        </ReactMarkdown>
      </div>
    );
  }
);

MarkdownContent.displayName = "MarkdownContent";
