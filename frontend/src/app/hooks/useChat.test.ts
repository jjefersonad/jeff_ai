import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useChat } from "./useChat";

const mockSubmit = vi.fn();

vi.mock("@langchain/langgraph-sdk/react", () => ({
  useStream: () => ({
    submit: mockSubmit,
    messages: [],
    values: {},
    isLoading: false,
    isThreadLoading: false,
    interrupt: undefined,
    getMessagesMetadata: vi.fn(),
  }),
}));

let mockThreadId: string | null = "thread-1";
const mockSetThreadId = vi.fn();

vi.mock("nuqs", () => ({
  useQueryState: () => [mockThreadId, mockSetThreadId],
}));

vi.mock("@/providers/ClientProvider", () => ({
  useClient: () => ({}),
}));

describe("useChat.sendMessage (chat-file-attachment REQ-004)", () => {
  beforeEach(() => {
    mockSubmit.mockReset();
    mockThreadId = "thread-1";
  });

  it("REQ-004: includes attachment_ids in the submitted message when provided", () => {
    const { result } = renderHook(() => useChat({ activeAssistant: null }));

    act(() => {
      result.current.sendMessage("hello", ["att-1", "att-2"]);
    });

    expect(mockSubmit).toHaveBeenCalledTimes(1);
    const [payload] = mockSubmit.mock.calls[0];
    const sentMessage = payload.messages[0];
    expect(sentMessage.content).toBe("hello");
    expect(sentMessage.additional_kwargs?.attachment_ids).toEqual([
      "att-1",
      "att-2",
    ]);
  });

  it("omits additional_kwargs.attachment_ids when no attachments are given", () => {
    const { result } = renderHook(() => useChat({ activeAssistant: null }));

    act(() => {
      result.current.sendMessage("hello");
    });

    const [payload] = mockSubmit.mock.calls[0];
    expect(
      payload.messages[0].additional_kwargs?.attachment_ids
    ).toBeUndefined();
  });

  it("exposes threadId so callers can scope an attachment upload to the current thread", () => {
    const { result } = renderHook(() => useChat({ activeAssistant: null }));
    expect(result.current.threadId).toBe("thread-1");
  });
});
