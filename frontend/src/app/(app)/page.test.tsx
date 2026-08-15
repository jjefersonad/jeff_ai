import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";

import ChatPage from "./page";

let mockSidebar: string | null = "1";
const mockSetSidebar = vi.fn((v: string | null) => {
  mockSidebar = v;
});
let mockThreadId: string | null = null;
const mockSetThreadId = vi.fn((v: string | null) => {
  mockThreadId = v;
});
let mockAssistantId: string | null = "unified";
const mockSetAssistantId = vi.fn((v: string | null) => {
  mockAssistantId = v;
});

vi.mock("nuqs", () => ({
  useQueryState: (key: string) => {
    if (key === "sidebar") return [mockSidebar, mockSetSidebar];
    if (key === "threadId") return [mockThreadId, mockSetThreadId];
    if (key === "assistantId") return [mockAssistantId, mockSetAssistantId];
    return [null, vi.fn()];
  },
}));

let mockIsMobile = false;
vi.mock("@/app/hooks/useIsMobile", () => ({
  useIsMobile: () => mockIsMobile,
}));

vi.mock("@/lib/config", () => ({
  getConfig: () => ({ assistantId: "unified" }),
  saveConfig: vi.fn(),
  DEFAULT_ASSISTANT_ID: "unified",
}));

const mockClient = {
  assistants: {
    get: vi.fn().mockResolvedValue({ assistant_id: "unified" }),
    search: vi.fn().mockResolvedValue([]),
  },
};

vi.mock("@/providers/ClientProvider", () => ({
  ClientProvider: ({ children }: { children: ReactNode }) => <>{children}</>,
  useClient: () => mockClient,
}));

vi.mock("@/providers/ChatProvider", () => ({
  ChatProvider: ({ children }: { children: ReactNode }) => <>{children}</>,
}));

vi.mock("@/app/components/ThreadList", () => ({
  ThreadList: ({ onClose }: { onClose?: () => void }) => (
    <div data-testid="thread-list-mock">
      {onClose && (
        <button
          aria-label="Close threads sidebar"
          onClick={onClose}
        >
          close
        </button>
      )}
    </div>
  ),
}));

vi.mock("@/app/components/ChatInterface", () => ({
  ChatInterface: () => <div data-testid="chat-interface-mock" />,
}));

vi.mock("@/components/ui/resizable", () => ({
  ResizablePanelGroup: ({ children }: { children: ReactNode }) => (
    <div data-testid="resizable-panel-group">{children}</div>
  ),
  ResizablePanel: ({
    children,
    id,
  }: {
    children: ReactNode;
    id?: string;
  }) => <div data-testid={`resizable-panel-${id}`}>{children}</div>,
  ResizableHandle: () => <div data-testid="resizable-handle" />,
}));

function setMatchMedia() {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
}

describe("ChatPage — thread-history panel responsive rendering (mobile-conversations-drawer-task-drawer-1)", () => {
  beforeEach(() => {
    mockSidebar = "1";
    mockThreadId = null;
    mockAssistantId = "unified";
    mockSetSidebar.mockClear();
    mockSetThreadId.mockClear();
    mockSetAssistantId.mockClear();
    setMatchMedia();
  });

  it("unit-1 / REQ-002 & REQ-004: on mobile, renders a fixed backdrop + drawer (w-[85vw] max-w-sm) wrapping ThreadList, with no ResizablePanel for thread-history", () => {
    mockIsMobile = true;

    render(<ChatPage />);

    const backdrop = screen.getByTestId("thread-history-backdrop");
    expect(backdrop.className).toContain("fixed");
    expect(backdrop.className).toContain("inset-0");
    expect(backdrop.className).toContain("bg-black/50");

    const drawer = screen.getByTestId("thread-history-drawer");
    expect(drawer.className).toContain("fixed");
    expect(drawer.className).toContain("inset-y-0");
    expect(drawer.className).toContain("left-0");
    expect(drawer.className).toContain("w-[85vw]");
    expect(drawer.className).toContain("max-w-sm");

    expect(drawer).toContainElement(screen.getByTestId("thread-list-mock"));
    expect(
      screen.queryByTestId("resizable-panel-thread-history")
    ).not.toBeInTheDocument();
    expect(screen.queryByTestId("resizable-handle")).not.toBeInTheDocument();
  });

  it("unit-2 / REQ-001: on desktop, renders the existing ResizablePanel/ResizableHandle structure with no backdrop or fixed drawer", () => {
    mockIsMobile = false;

    render(<ChatPage />);

    expect(
      screen.getByTestId("resizable-panel-thread-history")
    ).toBeInTheDocument();
    expect(screen.getByTestId("resizable-handle")).toBeInTheDocument();
    expect(screen.getByTestId("resizable-panel-chat")).toBeInTheDocument();

    expect(
      screen.queryByTestId("thread-history-backdrop")
    ).not.toBeInTheDocument();
    expect(
      screen.queryByTestId("thread-history-drawer")
    ).not.toBeInTheDocument();
  });

  it("unit-3 / REQ-004: the mobile drawer width is w-[85vw] max-w-sm, not NavSidebar's w-72", () => {
    mockIsMobile = true;

    render(<ChatPage />);

    const drawer = screen.getByTestId("thread-history-drawer");
    expect(drawer.className).not.toContain("w-72");
    expect(drawer.className).toContain("w-[85vw]");
    expect(drawer.className).toContain("max-w-sm");
  });
});

describe("ChatPage — mobile thread-history drawer dismissal (mobile-conversations-drawer-task-drawer-2 / REQ-003)", () => {
  beforeEach(() => {
    mockSidebar = "1";
    mockThreadId = null;
    mockAssistantId = "unified";
    mockSetSidebar.mockClear();
    mockSetThreadId.mockClear();
    mockSetAssistantId.mockClear();
    mockIsMobile = true;
    setMatchMedia();
  });

  it("unit-1: close via close button — clicking ThreadList's close button calls setSidebar(null)", async () => {
    const user = userEvent.setup();
    render(<ChatPage />);

    await user.click(
      screen.getByRole("button", { name: /close threads sidebar/i })
    );

    expect(mockSetSidebar).toHaveBeenCalledWith(null);
  });

  it("unit-2: close via backdrop tap — clicking the backdrop calls setSidebar(null)", async () => {
    const user = userEvent.setup();
    render(<ChatPage />);

    await user.click(screen.getByTestId("thread-history-backdrop"));

    expect(mockSetSidebar).toHaveBeenCalledWith(null);
  });

  it("unit-3: close via Escape key — pressing Esc while the mobile drawer is open calls setSidebar(null)", () => {
    render(<ChatPage />);

    fireEvent.keyDown(window, { key: "Escape" });

    expect(mockSetSidebar).toHaveBeenCalledWith(null);
  });

  it("unit-3: Escape does nothing on desktop — the effect is not attached when !isMobile", () => {
    mockIsMobile = false;
    render(<ChatPage />);

    fireEvent.keyDown(window, { key: "Escape" });

    expect(mockSetSidebar).not.toHaveBeenCalled();
  });
});

describe("ChatPage — saas-empresario-br-task-ux-3 unit-3 / REQ-004", () => {
  beforeEach(() => {
    mockSidebar = null;
    mockThreadId = "thread-1";
    mockAssistantId = "unified";
    mockSetSidebar.mockClear();
    mockSetThreadId.mockClear();
    mockSetAssistantId.mockClear();
    mockIsMobile = false;
    setMatchMedia();
  });

  it("labels the new conversation action Nova conversa, not New Thread", () => {
    render(<ChatPage />);

    expect(
      screen.getByRole("button", { name: /nova conversa/i })
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /new thread/i })
    ).not.toBeInTheDocument();
  });
});
