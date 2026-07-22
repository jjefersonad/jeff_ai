import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ThreadList } from "./ThreadList";

const mockDeleteThread = vi.fn();
const mockMutate = vi.fn();
const mockToastError = vi.fn();

vi.mock("sonner", () => ({
  toast: {
    error: (...args: unknown[]) => mockToastError(...args),
  },
}));

const THREAD_1 = {
  id: "t1",
  updatedAt: new Date(),
  status: "idle" as const,
  title: "Thread One",
  description: "desc",
};

let mockThreadsReturn: Record<string, unknown>;

vi.mock("@/app/hooks/useThreads", () => ({
  useThreads: () => mockThreadsReturn,
}));

let mockThreadId: string | null = null;
const mockSetThreadId = vi.fn((v: string | null) => {
  mockThreadId = v;
});

vi.mock("nuqs", () => ({
  useQueryState: () => [mockThreadId, mockSetThreadId],
}));

function renderThreadList(onThreadSelect = vi.fn()) {
  return render(<ThreadList onThreadSelect={onThreadSelect} />);
}

describe("ThreadList - delete action (fe-2)", () => {
  beforeEach(() => {
    mockDeleteThread.mockReset();
    mockMutate.mockReset();
    mockThreadId = null;
    mockSetThreadId.mockClear();
    mockThreadsReturn = {
      data: [[THREAD_1]],
      error: undefined,
      isLoading: false,
      size: 1,
      setSize: vi.fn(),
      mutate: mockMutate,
      deleteThread: mockDeleteThread,
    };
  });

  it("REQ-001: renders a delete action for each thread row", () => {
    renderThreadList();
    expect(
      screen.getByRole("button", { name: /delete thread/i })
    ).toBeInTheDocument();
  });

  it("REQ-002: clicking delete does not select the thread and opens the confirmation dialog", async () => {
    const onThreadSelect = vi.fn();
    const user = userEvent.setup();
    renderThreadList(onThreadSelect);

    await user.click(screen.getByRole("button", { name: /delete thread/i }));

    expect(onThreadSelect).not.toHaveBeenCalled();
    expect(mockDeleteThread).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("REQ-002: cancelling the dialog does not call deleteThread and the thread stays in the list", async () => {
    const user = userEvent.setup();
    renderThreadList();

    await user.click(screen.getByRole("button", { name: /delete thread/i }));
    await user.click(screen.getByRole("button", { name: /cancel/i }));

    expect(mockDeleteThread).not.toHaveBeenCalled();
    expect(screen.getByText("Thread One")).toBeInTheDocument();
  });

  it("REQ-002: confirming the dialog calls deleteThread with the thread id", async () => {
    mockDeleteThread.mockResolvedValueOnce(undefined);
    const user = userEvent.setup();
    renderThreadList();

    await user.click(screen.getByRole("button", { name: /delete thread/i }));
    const dialog = screen.getByRole("dialog");
    await user.click(
      screen.getByRole("button", { name: /^delete$/i, hidden: false })
    );

    expect(mockDeleteThread).toHaveBeenCalledTimes(1);
    expect(mockDeleteThread).toHaveBeenCalledWith("t1");
    void dialog;
  });
});

describe("ThreadList - active thread & error handling (fe-3)", () => {
  beforeEach(() => {
    mockDeleteThread.mockReset();
    mockMutate.mockReset();
    mockToastError.mockReset();
    mockThreadId = null;
    mockSetThreadId.mockClear();
    mockThreadsReturn = {
      data: [[THREAD_1]],
      error: undefined,
      isLoading: false,
      size: 1,
      setSize: vi.fn(),
      mutate: mockMutate,
      deleteThread: mockDeleteThread,
    };
  });

  it("REQ-004: clears the active thread when the deleted thread is the one open", async () => {
    mockThreadId = "t1";
    mockDeleteThread.mockResolvedValueOnce(undefined);
    const user = userEvent.setup();
    renderThreadList();

    await user.click(screen.getByRole("button", { name: /delete thread/i }));
    await user.click(screen.getByRole("button", { name: /^delete$/i }));

    expect(mockSetThreadId).toHaveBeenCalledTimes(1);
    expect(mockSetThreadId).toHaveBeenCalledWith(null);
  });

  it("REQ-004: leaves the active thread untouched when a different thread is deleted", async () => {
    mockThreadId = "some-other-thread";
    mockDeleteThread.mockResolvedValueOnce(undefined);
    const user = userEvent.setup();
    renderThreadList();

    await user.click(screen.getByRole("button", { name: /delete thread/i }));
    await user.click(screen.getByRole("button", { name: /^delete$/i }));

    expect(mockSetThreadId).not.toHaveBeenCalled();
  });

  it("REQ-005: shows an error toast and keeps the thread in the list when delete fails", async () => {
    mockThreadId = "t1";
    mockDeleteThread.mockRejectedValueOnce(new Error("boom"));
    const user = userEvent.setup();
    renderThreadList();

    await user.click(screen.getByRole("button", { name: /delete thread/i }));
    await user.click(screen.getByRole("button", { name: /^delete$/i }));

    expect(mockToastError).toHaveBeenCalledTimes(1);
    expect(mockSetThreadId).not.toHaveBeenCalled();
    expect(screen.getByText("Thread One")).toBeInTheDocument();
  });
});
