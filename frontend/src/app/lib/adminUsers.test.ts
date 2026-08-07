import { describe, it, expect, vi, afterEach } from "vitest";
import { createAdminUser, type CreateAdminUserError } from "./adminUsers";

describe("fix-user-registration-validation-error-display-task-frontend-1, REQ-003", () => {
  const originalFetch = global.fetch;

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("unit-1: single 422 validation error yields a readable message, not [object Object]", async () => {
    const body = JSON.stringify({
      detail: [
        {
          type: "string_too_short",
          loc: ["body", "password"],
          msg: "String should have at least 8 characters",
          input: "123456",
          ctx: { min_length: 8 },
        },
      ],
    });
    global.fetch = vi
      .fn()
      .mockResolvedValue(new Response(body, { status: 422 }));

    let caught: CreateAdminUserError | undefined;
    try {
      await createAdminUser({ username: "novo", password: "123456" });
    } catch (err) {
      caught = err as CreateAdminUserError;
    }

    expect(caught).toBeDefined();
    expect(caught?.message).not.toBe("[object Object]");
    expect(caught?.message).toContain(
      "String should have at least 8 characters"
    );
  });

  it("unit-2: multiple simultaneous 422 validation errors yield all messages joined into one readable string", async () => {
    const body = JSON.stringify({
      detail: [
        {
          type: "string_too_short",
          loc: ["body", "password"],
          msg: "String should have at least 8 characters",
          input: "123456",
          ctx: { min_length: 8 },
        },
        {
          type: "value_error",
          loc: ["body", "username"],
          msg: "Username must not be empty",
          input: "",
        },
      ],
    });
    global.fetch = vi
      .fn()
      .mockResolvedValue(new Response(body, { status: 422 }));

    let caught: CreateAdminUserError | undefined;
    try {
      await createAdminUser({ username: "", password: "123456" });
    } catch (err) {
      caught = err as CreateAdminUserError;
    }

    expect(caught?.message).toContain(
      "String should have at least 8 characters"
    );
    expect(caught?.message).toContain("Username must not be empty");
  });

  it("unit-3: a 409 with detail as a plain string is returned unchanged (regression guard)", async () => {
    const body = JSON.stringify({ detail: "Username already exists" });
    global.fetch = vi
      .fn()
      .mockResolvedValue(new Response(body, { status: 409 }));

    let caught: CreateAdminUserError | undefined;
    try {
      await createAdminUser({ username: "existing", password: "12345678" });
    } catch (err) {
      caught = err as CreateAdminUserError;
    }

    expect(caught?.message).toBe("Username already exists");
  });

  it("unit-4: missing/malformed detail falls back to res.statusText", async () => {
    const body = JSON.stringify({ detail: [{}] });
    global.fetch = vi.fn().mockResolvedValue(
      new Response(body, { status: 500, statusText: "Internal Server Error" })
    );

    let caught: CreateAdminUserError | undefined;
    try {
      await createAdminUser({ username: "x", password: "12345678" });
    } catch (err) {
      caught = err as CreateAdminUserError;
    }

    expect(caught?.message).toBe("Internal Server Error");
  });
});
