import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { DocumentHtmlPreview } from "./DocumentHtmlPreview";

const fetchAuthenticatedBlobUrl = vi.fn();

vi.mock("@/lib/api", () => ({
  fetchAuthenticatedBlobUrl: (...args: unknown[]) =>
    fetchAuthenticatedBlobUrl(...args),
  DownloadError: class DownloadError extends Error {
    kind: string;
    constructor(status: number, message: string, kind: string) {
      super(message);
      this.kind = kind;
    }
  },
}));

describe("DocumentHtmlPreview", () => {
  beforeEach(() => {
    fetchAuthenticatedBlobUrl.mockReset();
    fetchAuthenticatedBlobUrl.mockResolvedValue("blob:http://local/preview");
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("renders an iframe for /api/files/html/*.html, not an img", async () => {
    const url = "/api/files/html/20260807120000.html";
    render(<DocumentHtmlPreview url={url} />);

    await waitFor(() => {
      expect(screen.getByTitle(/preview html/i)).toBeInTheDocument();
    });

    const iframe = screen.getByTitle(/preview html/i);
    expect(iframe.tagName).toBe("IFRAME");
    expect(iframe).toHaveAttribute("src", "blob:http://local/preview");
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    expect(fetchAuthenticatedBlobUrl).toHaveBeenCalledWith(url);
  });

  it("always exposes a fallback link to the same url", async () => {
    const url = "/api/files/html/proposal.html";
    render(<DocumentHtmlPreview url={url} title="Proposta" />);

    const link = await screen.findByRole("link", { name: /abrir|proposta|preview/i });
    expect(link).toHaveAttribute("href", url);
    expect(link).toHaveAttribute("target", "_blank");
  });

  it("keeps the fallback link when the authenticated fetch fails", async () => {
    fetchAuthenticatedBlobUrl.mockRejectedValue(new Error("network"));
    const url = "/api/files/html/broken.html";
    render(<DocumentHtmlPreview url={url} />);

    const link = await screen.findByRole("link", { name: /abrir|preview/i });
    expect(link).toHaveAttribute("href", url);
    expect(screen.queryByTitle(/preview html/i)).not.toBeInTheDocument();
  });
});
