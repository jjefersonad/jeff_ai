import { useSyncExternalStore } from "react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, within, act } from "@testing-library/react";

import { ChatInterface } from "./ChatInterface";

const mockUseChatContext = vi.fn();

// `ChatInterface` is `React.memo`-wrapped. In the real app `useChatContext`
// subscribes to a real React Context, and Context updates always propagate
// through a memo boundary regardless of prop equality. A plain mocked
// function call does NOT reproduce that — RTL's `rerender()` with identical
// props hits the memo bailout and the component body never re-executes. This
// `useSyncExternalStore`-backed mock restores the "internal subscription
// update bypasses memo" behavior so `chat-empty-state-input` REQ-002's
// same-mount transition can be tested faithfully (see task-empty-2).
const chatContextListeners = new Set<() => void>();
function notifyChatContextChange() {
  chatContextListeners.forEach((listener) => listener());
}

vi.mock("@/providers/ChatProvider", () => ({
  useChatContext: () =>
    useSyncExternalStore(
      (listener) => {
        chatContextListeners.add(listener);
        return () => chatContextListeners.delete(listener);
      },
      () => mockUseChatContext()
    ),
}));

vi.mock("use-stick-to-bottom", () => ({
  useStickToBottom: () => ({
    scrollRef: { current: null },
    contentRef: { current: null },
  }),
}));

vi.mock("@/lib/api", () => ({
  uploadAttachment: vi.fn(),
  uploadReference: vi.fn(),
}));

vi.mock("@/app/components/ChatMessage", () => ({
  ChatMessage: () => <div data-testid="chat-message" />,
}));

vi.mock("@/app/components/ToolApprovalInterrupt", () => ({
  ToolApprovalInterrupt: () => null,
}));

vi.mock("@/app/components/EnvelopeApprovalInterrupt", () => ({
  EnvelopeApprovalInterrupt: () => null,
}));

vi.mock("@/app/components/AssistantButton", () => ({
  AssistantButton: () => <button aria-label="Assistant">Assistant</button>,
}));

vi.mock("@/app/components/AttachmentPicker", () => ({
  AttachmentPicker: () => null,
}));

vi.mock("@/app/components/TasksFilesSidebar", () => ({
  FilesPopover: () => null,
}));

function baseChatContext(overrides: Record<string, unknown> = {}) {
  return {
    stream: {},
    threadId: "thread-1",
    messages: [],
    todos: [],
    files: {},
    ui: [],
    setFiles: vi.fn(),
    isLoading: false,
    isThreadLoading: false,
    interrupt: undefined,
    sendMessage: vi.fn(),
    stopStream: vi.fn(),
    resumeInterrupt: vi.fn(),
    grantedCapabilities: [],
    ...overrides,
  };
}

describe("ChatInterface — chat-viewport-docking (task-dock-1)", () => {
  beforeEach(() => {
    mockUseChatContext.mockReset();
  });

  it("REQ-001: docks the input wrapper with fixed positioning, scoped to a containing-block root, when there are messages", () => {
    mockUseChatContext.mockReturnValue(
      baseChatContext({
        messages: [{ id: "1", type: "human", content: "hi" }],
      })
    );
    render(<ChatInterface assistant={null} assistantId="unified" />);

    const wrapper = screen.getByTestId("chat-input-dock");
    expect(wrapper.className).toMatch(/\bfixed\b/);
    expect(wrapper.className).toMatch(/\bbottom-0\b/);

    const root = screen.getByTestId("chat-interface-root");
    expect(root).toHaveStyle({ transform: "translateZ(0)" });
  });

  it("REQ-006: keeps toolbar button order and labels unchanged inside the docked wrapper", () => {
    mockUseChatContext.mockReturnValue(
      baseChatContext({
        messages: [{ id: "1", type: "human", content: "hi" }],
      })
    );
    render(<ChatInterface assistant={null} assistantId="unified" />);

    const wrapper = screen.getByTestId("chat-input-dock");
    const buttons = within(wrapper)
      .getAllByRole("button")
      .map((b) => b.getAttribute("aria-label") ?? b.textContent);

    expect(buttons).toEqual([
      "Assistant",
      "Anexar imagem de referência",
      expect.stringContaining("Send"),
    ]);
  });
});

describe("ChatInterface — chat-empty-state-input (task-empty-1)", () => {
  beforeEach(() => {
    mockUseChatContext.mockReset();
  });

  it("REQ-001: renders the input+toolbar wrapper with centered-flow classes (no fixed docking) when there are no messages", () => {
    mockUseChatContext.mockReturnValue(baseChatContext({ messages: [] }));
    render(<ChatInterface assistant={null} assistantId="unified" />);

    const wrapper = screen.getByTestId("chat-input-dock");
    // Centered-flow layout: the wrapper participates in normal flow and
    // centers the toolbar both axes instead of using fixed positioning.
    expect(wrapper.className).toMatch(/\bflex\b/);
    expect(wrapper.className).toMatch(/\bitems-center\b/);
    expect(wrapper.className).toMatch(/\bjustify-center\b/);
    // chat-viewport-docking's docked classes MUST NOT be applied when empty.
    expect(wrapper.className).not.toMatch(/\bfixed\b/);
    expect(wrapper.className).not.toMatch(/\bbottom-0\b/);
  });

  it("REQ-001: the centered empty-state wrapper still renders the toolbar (send button) — same underlying toolbar component", () => {
    mockUseChatContext.mockReturnValue(baseChatContext({ messages: [] }));
    render(<ChatInterface assistant={null} assistantId="unified" />);

    const wrapper = screen.getByTestId("chat-input-dock");
    expect(
      within(wrapper).getByRole("button", { name: /send/i })
    ).toBeTruthy();
  });
});

describe("ChatInterface — chat-viewport-docking (task-scroll-1)", () => {
  let resizeObserverCallback: ((entries: unknown[]) => void) | null = null;
  const originalResizeObserver = window.ResizeObserver;

  class MockResizeObserver {
    constructor(cb: (entries: unknown[]) => void) {
      resizeObserverCallback = cb;
    }
    observe() {}
    unobserve() {}
    disconnect() {}
  }

  beforeEach(() => {
    mockUseChatContext.mockReset();
    resizeObserverCallback = null;
    window.ResizeObserver =
      MockResizeObserver as unknown as typeof ResizeObserver;
  });

  afterEach(() => {
    window.ResizeObserver = originalResizeObserver;
  });

  function renderDocked() {
    mockUseChatContext.mockReturnValue(
      baseChatContext({
        messages: [{ id: "1", type: "human", content: "hi" }],
      })
    );
    const { container } = render(
      <ChatInterface assistant={null} assistantId="unified" />
    );
    const content = container.querySelector(
      '[data-testid="chat-messages-content"]'
    ) as HTMLElement | null;
    expect(content).not.toBeNull();
    return content as HTMLElement;
  }

  it("REQ-002 scenario 1: contentRef paddingBottom grows to match the input wrapper height", () => {
    const content = renderDocked();

    act(() => {
      resizeObserverCallback?.([{ contentRect: { height: 120 } }]);
    });

    expect(content.style.paddingBottom).toBe("120px");
  });

  it("REQ-002 scenario 2: contentRef paddingBottom shrinks back down when input height decreases", () => {
    const content = renderDocked();

    act(() => {
      resizeObserverCallback?.([{ contentRect: { height: 120 } }]);
    });
    act(() => {
      resizeObserverCallback?.([{ contentRect: { height: 48 } }]);
    });

    expect(content.style.paddingBottom).toBe("48px");
  });
});

describe("ChatInterface — chat-viewport-docking (task-mobile-1)", () => {
  beforeEach(() => {
    mockUseChatContext.mockReset();
  });

  it("REQ-003: root uses dvh-based sizing instead of relying solely on inherited vh height", () => {
    mockUseChatContext.mockReturnValue(baseChatContext({ messages: [] }));
    render(<ChatInterface assistant={null} assistantId="unified" />);

    const root = screen.getByTestId("chat-interface-root");
    expect(root.className).toMatch(/\b(?:max-)?h-dvh\b/);
  });
});

describe("ChatInterface — chat-viewport-docking (task-mobile-2)", () => {
  let visualViewport: {
    height: number;
    offsetTop: number;
    addEventListener: ReturnType<typeof vi.fn>;
    removeEventListener: ReturnType<typeof vi.fn>;
  };
  const originalVisualViewport = window.visualViewport;

  beforeEach(() => {
    mockUseChatContext.mockReset();
    visualViewport = {
      height: window.innerHeight,
      offsetTop: 0,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    };
    Object.defineProperty(window, 'visualViewport', {
      writable: true,
      value: visualViewport,
    });
  });

  afterEach(() => {
    Object.defineProperty(window, 'visualViewport', {
      writable: true,
      value: originalVisualViewport,
    });
  });

  it("REQ-003 scenario 1: on visualViewport resize (keyboard opens), input wrapper's translateY offset = window.innerHeight - visualViewport.height - visualViewport.offsetTop", () => {
    mockUseChatContext.mockReturnValue(
      baseChatContext({
        messages: [{ id: "1", type: "human", content: "hi" }], // Docked state
      })
    );
    render(<ChatInterface assistant={null} assistantId="unified" />);

    const inputWrapper = screen.getByTestId("chat-input-dock");
    
    // Simulate keyboard opening - visualViewport height decreases
    const keyboardHeight = 200;
    visualViewport.height = window.innerHeight - keyboardHeight;
    visualViewport.offsetTop = keyboardHeight; // Assuming offsetTop equals keyboard height for simplicity
    
    act(() => {
      visualViewport.addEventListener.mock.calls[0][1]("resize");
    });

    const expectedOffset = window.innerHeight - visualViewport.height - visualViewport.offsetTop;
    expect(inputWrapper).toHaveStyle({
      transform: `translateY(${-expectedOffset}px)`,
    });
  });

  it("REQ-003 scenario 2: on visualViewport resize back to full height (keyboard closes), offset returns to 0", () => {
    mockUseChatContext.mockReturnValue(
      baseChatContext({
        messages: [{ id: "1", type: "human", content: "hi" }], // Docked state
      })
    );
    render(<ChatInterface assistant={null} assistantId="unified" />);

    const inputWrapper = screen.getByTestId("chat-input-dock");
    
    // Simulate keyboard opening first
    const keyboardHeight = 200;
    visualViewport.height = window.innerHeight - keyboardHeight;
    visualViewport.offsetTop = keyboardHeight;
    
    act(() => {
      visualViewport.addEventListener.mock.calls[0][1]("resize");
    });
    
    // Simulate keyboard closing
    visualViewport.height = window.innerHeight;
    visualViewport.offsetTop = 0;
    
    act(() => {
      visualViewport.addEventListener.mock.calls[0][1]("resize");
    });

    expect(inputWrapper).toHaveStyle({
      transform: "translateY(0px)",
    });
  });

  it("REQ-003: visualViewport listener cleanup - unmounting removes listeners", () => {
    mockUseChatContext.mockReturnValue(
      baseChatContext({
        messages: [{ id: "1", type: "human", content: "hi" }],
      })
    );
    const { unmount } = render(<ChatInterface assistant={null} assistantId="unified" />);
    
    unmount();
    
    expect(visualViewport.removeEventListener).toHaveBeenCalledWith("resize", expect.any(Function));
    expect(visualViewport.removeEventListener).toHaveBeenCalledWith("scroll", expect.any(Function));
  });
});

describe("ChatInterface — chat-empty-state-input (task-empty-2)", () => {
  beforeEach(() => {
    mockUseChatContext.mockReset();
  });

  it("REQ-002: transitions from centered to docked when the first message arrives, without unmounting", () => {
    mockUseChatContext.mockReturnValue(baseChatContext({ messages: [] }));
    render(<ChatInterface assistant={null} assistantId="unified" />);

    const before = screen.getByTestId("chat-input-dock");
    expect(before.className).toMatch(/\bitems-center\b/);

    mockUseChatContext.mockReturnValue(
      baseChatContext({
        messages: [{ id: "1", type: "human", content: "hi" }],
      })
    );
    // Simulates a real Context update (the same mount receiving new
    // `messages` from `useChatContext`), not a remount.
    act(() => {
      notifyChatContextChange();
    });

    const after = screen.getByTestId("chat-input-dock");
    expect(after).toBe(before); // same DOM node — no unmount/remount
    expect(after.className).toMatch(/\bfixed\b/);
    expect(after.className).not.toMatch(/\bitems-center\b/);
  });
});

describe("ChatInterface — chat-empty-state-input (task-empty-3)", () => {
  beforeEach(() => {
    mockUseChatContext.mockReset();
  });

  it("REQ-003: a thread loaded with existing messages renders docked on the first render, never centered", () => {
    mockUseChatContext.mockReturnValue(
      baseChatContext({
        messages: [
          { id: "1", type: "human", content: "hi" },
          { id: "2", type: "ai", content: "hello" },
        ],
      })
    );
    render(<ChatInterface assistant={null} assistantId="unified" />);

    const wrapper = screen.getByTestId("chat-input-dock");
    expect(wrapper.className).toMatch(/\bfixed\b/);
    expect(wrapper.className).not.toMatch(/\bitems-center\b/);
  });

  it("REQ-003: a thread still loading (isThreadLoading) does not show the centered empty state either", () => {
    mockUseChatContext.mockReturnValue(
      baseChatContext({ messages: [], isThreadLoading: true })
    );
    render(<ChatInterface assistant={null} assistantId="unified" />);

    const wrapper = screen.getByTestId("chat-input-dock");
    expect(wrapper.className).not.toMatch(/\bitems-center\b/);
  });
});

describe("ChatInterface — saas-empresario-br-task-ux-3 unit-1 / REQ-004", () => {
  beforeEach(() => {
    mockUseChatContext.mockReset();
  });

  it("exports CHAT_EMPTY_JTBD with three literal prompts in JTBD order", async () => {
    const mod = await import("./ChatInterface");
    expect(
      mod.CHAT_EMPTY_JTBD.map((item: { label: string; prompt: string }) => item.label)
    ).toEqual([
      "Falar com o Jeff",
      "Registrar um cliente",
      "Conectar meu WhatsApp",
    ]);
    expect(
      mod.CHAT_EMPTY_JTBD.map((item: { label: string; prompt: string }) => item.prompt)
    ).toEqual([
      "Olá, Jeff. Preciso da sua ajuda no dia a dia do meu negócio.",
      "Me ajuda a cadastrar um contato no CRM.",
      "Como eu conecto o WhatsApp para falar com você pelo celular?",
    ]);
  });

  it("shows three clickable pt-BR suggestions in order on an empty conversation", () => {
    mockUseChatContext.mockReturnValue(baseChatContext({ messages: [] }));
    render(<ChatInterface assistant={null} assistantId="unified" />);

    const chips = screen.getAllByTestId("chat-empty-jtbd");
    expect(chips).toHaveLength(3);
    expect(chips.map((el) => el.textContent)).toEqual([
      "Falar com o Jeff",
      "Registrar um cliente",
      "Conectar meu WhatsApp",
    ]);
    for (const chip of chips) {
      expect(chip.tagName).toBe("BUTTON");
      expect(chip).not.toBeDisabled();
    }
  });

  it("does not render JTBD chips when the thread already has messages", () => {
    mockUseChatContext.mockReturnValue(
      baseChatContext({
        messages: [{ id: "1", type: "human", content: "hi" }],
      })
    );
    render(<ChatInterface assistant={null} assistantId="unified" />);
    expect(screen.queryAllByTestId("chat-empty-jtbd")).toHaveLength(0);
  });
});
