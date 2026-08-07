import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import UsersPage from "./page";

const {
  mockReplace,
  mockFetchAdminUsers,
  mockCreateAdminUser,
  mockPatchAdminUser,
} = vi.hoisted(() => ({
  mockReplace: vi.fn(),
  mockFetchAdminUsers: vi.fn(),
  mockCreateAdminUser: vi.fn(),
  mockPatchAdminUser: vi.fn(),
}));
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
    isRehydrating: false,
    user: mockAuthUser,
  }),
}));

vi.mock("@/app/lib/adminUsers", () => {
  return {
    fetchAdminUsers: (...args: unknown[]) => mockFetchAdminUsers(...args),
    createAdminUser: (...args: unknown[]) => mockCreateAdminUser(...args),
    patchAdminUser: (...args: unknown[]) => mockPatchAdminUser(...args),
  };
});

describe("UsersPage — admin route renders (user-management-frontend-1 unit-1 / REQ-001)", () => {
  beforeEach(() => {
    mockReplace.mockReset();
    mockFetchAdminUsers.mockReset();
    mockCreateAdminUser.mockReset();
    mockPatchAdminUser.mockReset();
    // Default empty list — the frontend-1 test only cares about the
    // admin-guard behaviour, not the list itself, but the page's effect
    // still calls `fetchAdminUsers` and needs a resolved Promise.
    mockFetchAdminUsers.mockResolvedValue([]);
    mockAuthUser = { username: "admin", role: "admin" };
  });

  it("REQ-001: WHEN role=admin THEN /admin/users renders the page content (no redirect)", () => {
    mockAuthUser = { username: "admin", role: "admin" };
    render(<UsersPage />);

    // No redirect happened
    expect(mockReplace).not.toHaveBeenCalled();

    // The page renders its expected heading — proves we did not block the
    // render with the non-admin guard.
    expect(
      screen.getByRole("heading", { name: /usuários/i })
    ).toBeInTheDocument();
  });

  it("REQ-001: WHEN role=user THEN /admin/users redirects away and renders no admin content", () => {
    mockAuthUser = { username: "alice", role: "user" };
    render(<UsersPage />);

    // The guard fires `router.replace("/")` for non-admins.
    expect(mockReplace).toHaveBeenCalledWith("/");

    // No admin-only heading reaches the DOM — the guard returns `null`
    // before any data is rendered.
    expect(
      screen.queryByRole("heading", { name: /usuários/i })
    ).not.toBeInTheDocument();
  });
});

describe("UsersPage — role filter narrows table (user-management-frontend-2 unit-1 / REQ-002)", () => {
  const mixedUsers = [
    {
      id: "admin-1",
      username: "admin",
      role: "admin",
      is_active: true,
      created_at: "2026-07-01T00:00:00Z",
    },
    {
      id: "user-1",
      username: "alice",
      role: "user",
      is_active: true,
      created_at: "2026-07-02T00:00:00Z",
    },
    {
      id: "user-2",
      username: "bob",
      role: "user",
      is_active: false,
      created_at: "2026-07-03T00:00:00Z",
    },
    {
      id: "admin-2",
      username: "ops",
      role: "admin",
      is_active: true,
      created_at: "2026-07-04T00:00:00Z",
    },
  ];

  beforeEach(() => {
    mockReplace.mockReset();
    mockFetchAdminUsers.mockReset();
    mockCreateAdminUser.mockReset();
    mockPatchAdminUser.mockReset();
    mockAuthUser = { username: "admin", role: "admin" };
    mockFetchAdminUsers.mockResolvedValue(mixedUsers);
  });

  it("REQ-002: WHEN the admin selects the role=admin filter THEN only role=admin rows remain visible in the table", async () => {
    const user = userEvent.setup();
    render(<UsersPage />);

    // Wait for the table to populate. We go through row-level scope to
    // avoid the duplicate "admin" text (the username cell of one row
    // literally contains "admin" — same string as the role cell of that
    // row, so a flat `findByText("admin")` is ambiguous).
    const table = await screen.findByRole("table");
    const initialRows = within(table).getAllByRole("row").slice(1); // skip header
    expect(initialRows).toHaveLength(mixedUsers.length);
    const usernamesByRow = initialRows.map((r) =>
      within(r).getAllByRole("cell")[0]?.textContent ?? ""
    );
    expect(usernamesByRow.sort()).toEqual(
      mixedUsers.map((u) => u.username).sort()
    );

    // The role filter is a Radix Select — open it and pick the "admin" option.
    const roleFilter = screen.getByRole("combobox", { name: /filtrar por role/i });
    await user.click(roleFilter);
    const adminOption = await screen.findByRole("option", { name: /^admin$/i });
    await user.click(adminOption);

    // Only the two admin rows stay in the table.
    const rowsAfter = within(table).getAllByRole("row").slice(1);
    expect(rowsAfter).toHaveLength(2);
    const usernamesAfter = rowsAfter.map(
      (r) => within(r).getAllByRole("cell")[0]?.textContent ?? ""
    );
    expect(usernamesAfter.sort()).toEqual(["admin", "ops"]);

    // The user-only rows are gone — the filter narrowed the table.
    expect(within(table).queryByText("alice")).not.toBeInTheDocument();
    expect(within(table).queryByText("bob")).not.toBeInTheDocument();
  });
});

describe("UsersPage — create form (user-management-frontend-3 / REQ-003)", () => {
  const initialUsers = [
    {
      id: "admin-1",
      username: "admin",
      role: "admin",
      is_active: true,
      created_at: "2026-07-01T00:00:00Z",
    },
  ];

  beforeEach(() => {
    mockReplace.mockReset();
    mockFetchAdminUsers.mockReset();
    mockCreateAdminUser.mockReset();
    mockPatchAdminUser.mockReset();
    mockAuthUser = { username: "admin", role: "admin" };
    mockFetchAdminUsers.mockResolvedValue(initialUsers);
  });

  it("unit-1: REQ-003 — successful submission adds the new user to the visible list without a full page reload", async () => {
    const created = {
      id: "user-new",
      username: "newbie",
      role: "user",
      is_active: true,
      created_at: "2026-07-10T00:00:00Z",
    };
    mockCreateAdminUser.mockResolvedValue(created);

    const user = userEvent.setup();
    render(<UsersPage />);

    // Wait for the initial list to render — scope to the first <td> (the
    // username cell) to avoid the duplicate "admin" text (username cell +
    // role cell of the admin row).
    const table = await screen.findByRole("table");
    const initialUsernames = within(table)
      .getAllByRole("row")
      .slice(1) // skip header
      .map((r) => within(r).getAllByRole("cell")[0]?.textContent ?? "");
    expect(initialUsernames).toEqual(["admin"]);

    // Fill the create form and submit. The form lives outside the table
    // (it's a panel above the listing) so a flat query is safe here.
    await user.type(screen.getByLabelText(/^usuário$/i), "newbie");
    await user.type(screen.getByLabelText(/^senha$/i), "supersecret");
    await user.click(screen.getByRole("button", { name: /criar/i }));

    // The mock was called with the typed values.
    expect(mockCreateAdminUser).toHaveBeenCalledWith({
      username: "newbie",
      password: "supersecret",
      role: "user",
    });

    // The new user appears in the table without a full reload (no
    // `replace` on the router was triggered).
    const finalUsernames = within(table)
      .getAllByRole("row")
      .slice(1) // skip header
      .map((r) => within(r).getAllByRole("cell")[0]?.textContent ?? "");
    expect(finalUsernames.sort()).toEqual(["admin", "newbie"]);
    expect(mockReplace).not.toHaveBeenCalled();

    // Username + password fields are cleared after success.
    expect(screen.getByLabelText(/^usuário$/i)).toHaveValue("");
    expect(screen.getByLabelText(/^senha$/i)).toHaveValue("");
  });

  it("unit-2: REQ-003 — a 422 response displays the error inline and does NOT clear the fields the user already filled in", async () => {
    const err = new Error("String should have at least 8 characters") as Error & {
      status: number;
    };
    err.status = 422;
    mockCreateAdminUser.mockRejectedValue(err);

    const user = userEvent.setup();
    render(<UsersPage />);

    await screen.findByRole("table");

    await user.type(screen.getByLabelText(/^usuário$/i), "carol");
    await user.type(screen.getByLabelText(/^senha$/i), "short"); // 5 chars → 422
    await user.click(screen.getByRole("button", { name: /criar/i }));

    // The form preserves the user's input on a 422 response — REQ-003
    // scenario "Erro de validação exibido no formulário".
    const usernameField = screen.getByLabelText(/^usuário$/i) as HTMLInputElement;
    const passwordField = screen.getByLabelText(/^senha$/i) as HTMLInputElement;
    expect(usernameField.value).toBe("carol");
    expect(passwordField.value).toBe("short");

    // The error message from the API is rendered inline, with role=alert
    // so screen readers announce it.
    const alert = screen.getByRole("alert");
    expect(alert.textContent).toMatch(/8/);

    // No router navigation on a 422 — the user is still on /admin/users.
    expect(mockReplace).not.toHaveBeenCalled();

    // The table did not gain the new user (the request never succeeded).
    const table = screen.getByRole("table");
    expect(within(table).queryByText("carol")).not.toBeInTheDocument();
  });
});

describe("UsersPage — status toggle (user-management-frontend-4 unit-1 / REQ-004)", () => {
  const initialUsers = [
    {
      id: "admin-1",
      username: "admin",
      role: "admin",
      is_active: true,
      created_at: "2026-07-01T00:00:00Z",
    },
    {
      id: "user-1",
      username: "alice",
      role: "user",
      is_active: true,
      created_at: "2026-07-02T00:00:00Z",
    },
  ];

  beforeEach(() => {
    mockReplace.mockReset();
    mockFetchAdminUsers.mockReset();
    mockCreateAdminUser.mockReset();
    mockPatchAdminUser.mockReset();
    mockAuthUser = { username: "admin", role: "admin" };
    mockFetchAdminUsers.mockResolvedValue(initialUsers);
  });

  it("unit-1: REQ-004 — clicking the status toggle MUST call PATCH /admin/users/{id} with is_active=false and reflect the new status on a 200 response", async () => {
    // Mock the PATCH to return the updated user (is_active=false). The
    // page MUST update the row in place — no full reload, no router
    // navigation.
    const updatedAlice = {
      id: "user-1",
      username: "alice",
      role: "user",
      is_active: false,
      created_at: "2026-07-02T00:00:00Z",
    };
    mockPatchAdminUser.mockResolvedValue(updatedAlice);

    const user = userEvent.setup();
    render(<UsersPage />);

    // Wait for both rows to render. The switch for the alice row is
    // identified by its accessible name (the row's "Ativo" text plus the
    // username so we don't click the admin's own switch by accident).
    const table = await screen.findByRole("table");
    const aliceRow = within(table)
      .getAllByRole("row")
      .slice(1) // skip header
      .find((r) => within(r).queryByText("alice"));
    expect(aliceRow).toBeDefined();
    // Sanity: alice starts as "Ativo".
    expect(within(aliceRow!).getByText(/^ativo$/i)).toBeInTheDocument();

    // The status toggle for that row is the only Switch in the table for
    // the alice row. Use a scoped query inside the row.
    const switchesInRow = within(aliceRow!).getAllByRole("switch");
    expect(switchesInRow).toHaveLength(1);
    const aliceSwitch = switchesInRow[0]!;
    expect(aliceSwitch).toHaveAttribute("aria-checked", "true");

    await user.click(aliceSwitch);

    // PATCH was called with the right id and payload.
    expect(mockPatchAdminUser).toHaveBeenCalledWith("user-1", {
      is_active: false,
    });
    expect(mockPatchAdminUser).toHaveBeenCalledTimes(1);

    // After the 200 response the row now shows "Inativo" — the displayed
    // status reflects the new server-side value.
    const aliceRowAfter = within(table)
      .getAllByRole("row")
      .slice(1)
      .find((r) => within(r).queryByText("alice"));
    expect(aliceRowAfter).toBeDefined();
    expect(within(aliceRowAfter!).getByText(/^inativo$/i)).toBeInTheDocument();
    // The switch's aria-checked now reflects the updated status.
    expect(
      within(aliceRowAfter!).getByRole("switch")
    ).toHaveAttribute("aria-checked", "false");

    // No router navigation on a successful toggle.
    expect(mockReplace).not.toHaveBeenCalled();
  });
});

describe("UsersPage — 409 error not applied optimistically (user-management-frontend-4 unit-2 / REQ-004)", () => {
  const initialUsers = [
    {
      id: "admin-1",
      username: "admin",
      role: "admin",
      is_active: true,
      created_at: "2026-07-01T00:00:00Z",
    },
    {
      id: "user-1",
      username: "alice",
      role: "user",
      is_active: true,
      created_at: "2026-07-02T00:00:00Z",
    },
  ];

  beforeEach(() => {
    mockReplace.mockReset();
    mockFetchAdminUsers.mockReset();
    mockCreateAdminUser.mockReset();
    mockPatchAdminUser.mockReset();
    mockAuthUser = { username: "admin", role: "admin" };
    mockFetchAdminUsers.mockResolvedValue(initialUsers);
  });

  it("unit-2: REQ-004 — a 409 from PATCH displays the error to the user AND leaves the row's displayed state unchanged", async () => {
    // The backend returns 409 (auto-lockout guard) — `patchAdminUser`
    // rejects with an Error whose `.status === 409`. The page MUST:
    //   1. show the error message to the user (role=alert), and
    //   2. leave alice's row displaying "Ativo" (no optimistic update
    //      that would need to be reverted awkwardly).
    const err = new Error(
      "Não é possível desativar o último administrador ativo"
    ) as Error & { status: number };
    err.status = 409;
    mockPatchAdminUser.mockRejectedValue(err);

    const user = userEvent.setup();
    render(<UsersPage />);

    // Wait for the rows to render.
    const table = await screen.findByRole("table");
    const aliceRowBefore = within(table)
      .getAllByRole("row")
      .slice(1)
      .find((r) => within(r).queryByText("alice"));
    expect(aliceRowBefore).toBeDefined();
    expect(within(aliceRowBefore!).getByText(/^ativo$/i)).toBeInTheDocument();

    // Click the switch for the alice row.
    const aliceSwitch = within(aliceRowBefore!).getByRole("switch");
    expect(aliceSwitch).toHaveAttribute("aria-checked", "true");
    await user.click(aliceSwitch);

    // PATCH was attempted with the right payload.
    expect(mockPatchAdminUser).toHaveBeenCalledWith("user-1", {
      is_active: false,
    });

    // The error from the API is displayed to the user (role=alert).
    // There may be multiple alerts on the page (one for the table, one for
    // the create form), so we assert on the one whose text mentions the
    // 409 message — the row-level error.
    const alerts = await screen.findAllByRole("alert");
    const rowError = alerts.find((a) =>
      a.textContent?.match(/administrador/i)
    );
    expect(rowError).toBeDefined();
    expect(rowError!.textContent).toMatch(/último administrador/i);

    // The row's displayed state is UNCHANGED — no optimistic update.
    // Alice is still "Ativo" and the switch's aria-checked is still true.
    const aliceRowAfter = within(table)
      .getAllByRole("row")
      .slice(1)
      .find((r) => within(r).queryByText("alice"));
    expect(aliceRowAfter).toBeDefined();
    expect(within(aliceRowAfter!).getByText(/^ativo$/i)).toBeInTheDocument();
    expect(
      within(aliceRowAfter!).getByRole("switch")
    ).toHaveAttribute("aria-checked", "true");

    // No router navigation on a 409.
    expect(mockReplace).not.toHaveBeenCalled();
  });
});
