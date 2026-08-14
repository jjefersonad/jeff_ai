/**
 * Tests for the `?gmail_connected` query handling on `/email`
 * (gmail-account-oauth-connection-task-frontend-2-unit-1).
 *
 * The OAuth callback redirects the browser to
 * `{FRONTEND_ORIGIN}/email?gmail_connected=1|0` after the user finishes
 * (or aborts) the Google consent flow. This page is responsible for:
 *   - showing a success toast and refetching the accounts list on `=1`
 *   - showing an error toast on `=0`
 *   - stripping the `gmail_connected` query param from the URL via
 *     `window.history.replaceState` (no Next.js navigation — that would
 *     re-mount the page and re-fire the effect, risking duplicate toasts
 *     / refetches)
 *
 * The unit under test is the `useEffect` inside the page component; the
 * tab UI is irrelevant here, so the assertions only check the side
 * effects (toast, accounts refetch, URL strip).
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

import EmailPage from "./page";

const mockListEmailAccounts = vi.fn();
const mockToastSuccess = vi.fn();
const mockToastError = vi.fn();
const mockReplaceState = vi.fn();

// Captura o `?gmail_connected=...` que o component vai ler.
let mockSearchParamsValue: string | null = null;

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  // O `useSearchParams` do Next devolve um `ReadonlyURLSearchParams`;
  // nosso mock expõe `get` (que é o único membro usado pela page) e
  // ignora o resto. Retornamos um valor cuja leitura depende do
  // estado externo para podermos controlar o cenário.
  useSearchParams: () => ({
    get: (key: string) =>
      key === "gmail_connected" ? mockSearchParamsValue : null,
    toString: () =>
      mockSearchParamsValue === null
        ? ""
        : `gmail_connected=${mockSearchParamsValue}`,
  }),
}));

vi.mock("@/lib/email", async () => {
  const actual = await vi.importActual<typeof import("@/lib/email")>("@/lib/email");
  return {
    ...actual,
    listEmailAccounts: (...args: unknown[]) => mockListEmailAccounts(...args),
  };
});

vi.mock("sonner", () => ({
  toast: {
    success: (...args: unknown[]) => mockToastSuccess(...args),
    error: (...args: unknown[]) => mockToastError(...args),
  },
}));

// `window.history.replaceState` não tem efeito em jsdom (o que é ótimo
// para o teste — não tenta navegar de verdade) mas queremos ASSERT que
// o component o chamou com o URL stripado.
const originalReplaceState = window.history.replaceState;
beforeEach(() => {
  mockListEmailAccounts.mockReset();
  mockToastSuccess.mockReset();
  mockToastError.mockReset();
  mockReplaceState.mockReset();
  mockSearchParamsValue = null;
  mockListEmailAccounts.mockResolvedValue([]);
  window.history.replaceState = mockReplaceState as typeof window.history.replaceState;
});

afterEach(() => {
  window.history.replaceState = originalReplaceState;
});

describe("EmailPage gmail_connected query (gmail-account-oauth-connection-task-frontend-2)", () => {
  // ----- unit-1 (REQ-002 + REQ-004): success + error + URL strip -----
  it("unit-1: ?gmail_connected=1 shows success toast, refetches accounts, and strips the query param", async () => {
    mockSearchParamsValue = "1";

    render(<EmailPage />);

    await waitFor(() => {
      expect(mockToastSuccess).toHaveBeenCalledTimes(1);
    });
    expect(mockToastError).not.toHaveBeenCalled();
    // `listEmailAccounts` is called on mount; we need to count
    // occurrences AFTER the effect fires the refetch.
    await waitFor(() => {
      // The page calls `refreshAccounts()` in two effects: the mount
      // effect AND the gmail_connected effect. So at least 2 calls
      // when `gmail_connected` is present.
      expect(mockListEmailAccounts.mock.calls.length).toBeGreaterThanOrEqual(2);
    });

    // URL was stripped via `history.replaceState`.
    expect(mockReplaceState).toHaveBeenCalledTimes(1);
    const [, , urlArg] = mockReplaceState.mock.calls[0] as [
      unknown,
      unknown,
      string | URL | null | undefined,
    ];
    const stripped = String(urlArg ?? "");
    // The query param `gmail_connected` is no longer in the URL.
    expect(stripped).not.toMatch(/gmail_connected/);
  });

  it("unit-1b: ?gmail_connected=0 shows error toast (no success) and strips the query param", async () => {
    mockSearchParamsValue = "0";

    render(<EmailPage />);

    await waitFor(() => {
      expect(mockToastError).toHaveBeenCalledTimes(1);
    });
    expect(mockToastSuccess).not.toHaveBeenCalled();
    expect(mockReplaceState).toHaveBeenCalledTimes(1);
    const [, , urlArg] = mockReplaceState.mock.calls[0] as [
      unknown,
      unknown,
      string | URL | null | undefined,
    ];
    const stripped = String(urlArg ?? "");
    expect(stripped).not.toMatch(/gmail_connected/);
  });

  it("unit-1c: when no gmail_connected query param, no toast fires and URL is untouched", async () => {
    mockSearchParamsValue = null;

    render(<EmailPage />);

    // Wait a tick to let any effects flush.
    await waitFor(() => {
      expect(mockListEmailAccounts).toHaveBeenCalled();
    });
    expect(mockToastSuccess).not.toHaveBeenCalled();
    expect(mockToastError).not.toHaveBeenCalled();
    expect(mockReplaceState).not.toHaveBeenCalled();
    // Page still renders its title.
    expect(screen.getByRole("heading", { name: /email/i })).toBeInTheDocument();
  });
});
