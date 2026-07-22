import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { AttachmentPicker } from "./AttachmentPicker";

function Harness() {
  const [attachments, setAttachments] = useState<File[]>([]);
  return (
    <AttachmentPicker
      attachments={attachments}
      onAttachmentsChange={setAttachments}
    />
  );
}

function makeFile(name: string, content = "content", type = "") {
  return new File([content], name, { type });
}

describe("AttachmentPicker (chat-file-attachment REQ-001)", () => {
  let fetchSpy: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);
  });

  it("REQ-001: selecting a supported file type adds it to pending state and displays it", async () => {
    const user = userEvent.setup();
    render(<Harness />);

    const input = screen.getByLabelText(/attach a file/i);
    await user.upload(input, makeFile("report.pdf", "%PDF-1.4", "application/pdf"));

    expect(screen.getByText("report.pdf")).toBeInTheDocument();
  });

  it("REQ-001: selecting an unsupported file type shows an inline error and calls no network request", async () => {
    // applyAccept: false — the `accept` attribute is a UX hint, not a security
    // boundary (drag-and-drop bypasses it entirely); the JS-level check under
    // test must reject the file regardless of what the picker dialog allowed.
    const user = userEvent.setup({ applyAccept: false });
    render(<Harness />);

    const input = screen.getByLabelText(/attach a file/i);
    await user.upload(input, makeFile("virus.exe", "MZ", "application/octet-stream"));

    expect(
      screen.getByText(/unsupported file type/i)
    ).toBeInTheDocument();
    expect(screen.getByText(/pdf/i)).toBeInTheDocument();
    expect(screen.queryByText("virus.exe")).not.toBeInTheDocument();
    expect(fetchSpy).not.toHaveBeenCalled();
  });
});
