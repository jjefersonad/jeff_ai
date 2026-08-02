import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";

import { ImageZoomModal } from "./ImageZoomModal";

// Dialog uses @radix-ui/react-dialog which requires the dialog to be portaled.
// The Radix portal target is document.body by default, so jsdom needs the
// portal target. Default jsdom already has <body>, which is enough.

describe("ImageZoomModal", () => {
  it("renders nothing when src is null", () => {
    const onOpenChange = vi.fn();
    render(
      <ImageZoomModal src={null} alt="anything" onOpenChange={onOpenChange} />
    );

    // Modal is closed, so no image is in the document
    expect(screen.queryByRole("img")).toBeNull();
  });

  it("renders the image when src is provided", () => {
    const onOpenChange = vi.fn();
    render(
      <ImageZoomModal
        src="data:image/svg+xml;base64,PHN2Zy8+"
        alt="test image"
        onOpenChange={onOpenChange}
      />
    );

    const img = screen.getByRole("img");
    expect(img).toHaveAttribute("src", "data:image/svg+xml;base64,PHN2Zy8+");
    expect(img).toHaveAttribute("alt", "test image");
  });

  it("uses sr-only title for accessibility when alt is empty", () => {
    render(
      <ImageZoomModal src="data:image/png;base64,xxx" alt="" onOpenChange={() => {}} />
    );

    // Radix renders DialogTitle with sr-only class — still in DOM, hidden visually.
    // We just check it has the expected text content.
    expect(screen.getByText("Imagem ampliada")).toBeInTheDocument();
  });

  it("calls onOpenChange(false) when close button is clicked", async () => {
    const user = userEvent.setup();
    const onOpenChange = vi.fn();
    render(
      <ImageZoomModal
        src="data:image/png;base64,xxx"
        alt="x"
        onOpenChange={onOpenChange}
      />
    );

    // Radix Dialog renders a close button (X icon) automatically
    const closeButton = screen.getByRole("button", { name: /close/i });
    await user.click(closeButton);

    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("calls onOpenChange(false) when ESC is pressed", async () => {
    const user = userEvent.setup();
    const onOpenChange = vi.fn();
    render(
      <ImageZoomModal
        src="data:image/png;base64,xxx"
        alt="x"
        onOpenChange={onOpenChange}
      />
    );

    await user.keyboard("{Escape}");

    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("applies max-w/max-h to keep image within viewport", () => {
    render(
      <ImageZoomModal
        src="data:image/png;base64,xxx"
        alt="x"
        onOpenChange={() => {}}
      />
    );

    const img = screen.getByRole("img");
    // Tailwind utility classes — we check the className contains both
    const cls = img.getAttribute("class") ?? "";
    expect(cls).toContain("max-w-[90vw]");
    expect(cls).toContain("max-h-[90vh]");
    expect(cls).toContain("object-contain");
  });
});