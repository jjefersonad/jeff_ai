import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import UsagePage from "./page";

const mockReplace = vi.fn();
const mockApiFetch = vi.fn();
let mockAuthUser: { username: string; role: "admin" | "user" } | null = {
  username: "admin",
  role: "admin",
};

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: mockReplace }),
}));

vi.mock("@/providers/AuthProvider", () => ({
  useAuth: () => ({
    isAuthenticated: mockAuthUser !== null,
    user: mockAuthUser,
  }),
}));

vi.mock("@/lib/api", () => ({
  apiFetch: (...args: unknown[]) => mockApiFetch(...args),
  ApiError: class ApiError extends Error {
    status: number;
    constructor(status: number, message: string) {
      super(message);
      this.status = status;
    }
  },
  parseErrorMessage: async () => "error",
}));

describe("UsagePage — admin period query (reporting-2 unit-2 / REQ-002)", () => {
  beforeEach(() => {
    mockReplace.mockReset();
    mockApiFetch.mockReset();
    mockAuthUser = { username: "admin", role: "admin" };
    mockApiFetch.mockResolvedValue(
      new Response(
        JSON.stringify({
          prompt_tokens: 120,
          completion_tokens: 80,
          total_tokens: 200,
          filters: { from: "2026-07-01T00:00:00", to: "2026-07-25T23:59:59" },
        }),
        { status: 200 }
      )
    );
  });

  it("REQ-006: WHEN role=user THEN direct URL access redirects away", () => {
    mockAuthUser = { username: "alice", role: "user" };
    render(<UsagePage />);
    expect(mockReplace).toHaveBeenCalledWith("/");
    expect(screen.queryByRole("heading", { name: /consumo/i })).not.toBeInTheDocument();
  });

  it("WHEN admin selects from/to and requests usage THEN calls GET /api/usage and renders totals", async () => {
    const user = userEvent.setup();
    render(<UsagePage />);

    const fromInput = screen.getByLabelText("De");
    const toInput = screen.getByLabelText("Até");
    await user.clear(fromInput);
    await user.type(fromInput, "2026-07-01");
    await user.clear(toInput);
    await user.type(toInput, "2026-07-25");
    await user.click(screen.getByRole("button", { name: /consultar/i }));

    await waitFor(() => {
      expect(mockApiFetch).toHaveBeenCalled();
    });

    const [path] = mockApiFetch.mock.calls[0] as [string];
    expect(path).toMatch(/^\/api\/usage\?/);
    expect(path).toContain("from=");
    expect(path).toContain("to=");
    expect(path).toContain("2026-07-01");
    expect(path).toContain("2026-07-25");

    expect(await screen.findByText("120")).toBeInTheDocument();
    expect(screen.getByText("80")).toBeInTheDocument();
    expect(screen.getByText("200")).toBeInTheDocument();
  });
});
