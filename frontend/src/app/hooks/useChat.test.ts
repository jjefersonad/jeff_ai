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

describe("useChat.sendMessage profile overlay (ui-2 unit-1 / REQ-002)", () => {
  beforeEach(() => {
    mockSubmit.mockReset();
    mockThreadId = "thread-1";
  });

  it("WHEN profileId is set THEN stream.submit includes configurable.profile_id", () => {
    const { result } = renderHook(() =>
      useChat({ activeAssistant: null, profileId: "profile-marketing" })
    );

    act(() => {
      result.current.sendMessage("hello");
    });

    expect(mockSubmit).toHaveBeenCalledTimes(1);
    const [, options] = mockSubmit.mock.calls[0];
    expect(options.config.configurable.profile_id).toBe("profile-marketing");
  });

  it("WHEN profileId changes THEN the next submit sends the new id (REQ-006)", () => {
    const { result, rerender } = renderHook(
      ({ profileId }: { profileId: string }) =>
        useChat({ activeAssistant: null, profileId }),
      { initialProps: { profileId: "profile-a" } }
    );

    act(() => {
      result.current.sendMessage("first");
    });
    expect(mockSubmit.mock.calls[0][1].config.configurable.profile_id).toBe(
      "profile-a"
    );

    rerender({ profileId: "profile-b" });
    act(() => {
      result.current.sendMessage("second");
    });
    expect(mockSubmit.mock.calls[1][1].config.configurable.profile_id).toBe(
      "profile-b"
    );
  });
});

describe("useChat.sendMessage empty profile (ui-2 unit-2 / REQ-002)", () => {
  beforeEach(() => {
    mockSubmit.mockReset();
    mockThreadId = "thread-1";
  });

  it("WHEN profileId is omitted THEN stream.submit does not send a fabricated profile_id", () => {
    const { result } = renderHook(() => useChat({ activeAssistant: null }));

    act(() => {
      result.current.sendMessage("hello");
    });

    const [, options] = mockSubmit.mock.calls[0];
    expect(options.config.configurable?.profile_id).toBeUndefined();
  });

  it("WHEN profileId is cleared THEN the next submit omits configurable.profile_id", () => {
    const { result, rerender } = renderHook(
      ({ profileId }: { profileId?: string }) =>
        useChat({ activeAssistant: null, profileId }),
      { initialProps: { profileId: "profile-marketing" as string | undefined } }
    );

    act(() => {
      result.current.sendMessage("with profile");
    });
    expect(mockSubmit.mock.calls[0][1].config.configurable.profile_id).toBe(
      "profile-marketing"
    );

    rerender({ profileId: undefined });
    act(() => {
      result.current.sendMessage("default agent");
    });
    expect(
      mockSubmit.mock.calls[1][1].config.configurable?.profile_id
    ).toBeUndefined();
  });
});
