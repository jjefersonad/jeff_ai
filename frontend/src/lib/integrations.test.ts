import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";

import { ApiError } from "./api";
import {
  buildDeepLinkHref,
  createTelegramLinkCode,
  deleteUserIntegration,
  getChannelLinkConfig,
  getIntegrationTypeMeta,
  listUserIntegrations,
} from "./integrations";

describe("createTelegramLinkCode (telegram-integration-frontend-registration-task-lib-1 unit-1/2 / REQ-002)", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    process.env.NEXT_PUBLIC_API_URL = "http://backend.test";
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("WHEN backend responds 201 THEN resolves to {code, expires_at} via apiFetch", async () => {
    const payload = { code: "ABC123", expires_at: "2026-08-09T12:00:00Z" };
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify(payload), { status: 201 }));
    global.fetch = fetchMock;

    const result = await createTelegramLinkCode();

    expect(result).toEqual(payload);
    const [url, options] = fetchMock.mock.calls[0];
    expect(String(url)).toContain("/api/integrations/telegram/link-code");
    expect(options).toMatchObject({ method: "POST", credentials: "include" });
  });

  it("WHEN backend responds non-2xx THEN throws ApiError with parsed message", async () => {
    const fetchMock = vi.fn(
      async () =>
        new Response(JSON.stringify({ detail: "Unauthorized" }), { status: 401 })
    );
    global.fetch = fetchMock;

    await expect(createTelegramLinkCode()).rejects.toMatchObject({
      status: 401,
      message: "Unauthorized",
    });
    await expect(createTelegramLinkCode()).rejects.toBeInstanceOf(ApiError);
  });
});

describe("listUserIntegrations (user-integrations-list-delete-task-lib-1 unit-1 / user-integrations-list REQ-001)", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    process.env.NEXT_PUBLIC_API_URL = "http://backend.test";
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("WHEN backend responds 200 with an array THEN resolves to it via apiFetch", async () => {
    const payload = [
      {
        id: "i1",
        user_id: "u1",
        integration_type: "telegram",
        config: { chat_id: "123" },
        created_at: "2026-08-01T00:00:00Z",
        updated_at: "2026-08-01T00:00:00Z",
      },
    ];
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify(payload), { status: 200 }));
    global.fetch = fetchMock;

    const result = await listUserIntegrations();

    expect(result).toEqual(payload);
    const [url, options] = fetchMock.mock.calls[0];
    expect(String(url)).toContain("/api/integrations");
    expect(options).toMatchObject({ credentials: "include" });
  });
});

describe("deleteUserIntegration (user-integrations-list-delete-task-lib-1 unit-2 / user-integrations-delete REQ-002)", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    process.env.NEXT_PUBLIC_API_URL = "http://backend.test";
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("WHEN backend responds 204 THEN resolves to void", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    global.fetch = fetchMock;

    await expect(deleteUserIntegration("i1")).resolves.toBeUndefined();
    const [url, options] = fetchMock.mock.calls[0];
    expect(String(url)).toContain("/api/integrations/i1");
    expect(options).toMatchObject({ method: "DELETE" });
  });

  it("WHEN backend responds non-2xx THEN throws ApiError with parsed message", async () => {
    const fetchMock = vi.fn(
      async () => new Response(JSON.stringify({ detail: "Not found" }), { status: 404 })
    );
    global.fetch = fetchMock;

    await expect(deleteUserIntegration("i1")).rejects.toMatchObject({
      status: 404,
      message: "Not found",
    });
  });
});

describe("getIntegrationTypeMeta (user-integrations-list-delete-task-lib-1 unit-3 / user-integrations-list REQ-002)", () => {
  it("WHEN type is known THEN resolves to its documented label/icon", () => {
    expect(getIntegrationTypeMeta("telegram").label).toBe("Telegram");
    expect(getIntegrationTypeMeta("whatsapp_business").label).toBe("WhatsApp Business");
    expect(getIntegrationTypeMeta("smtp").label).toBe("SMTP");
  });

  it("WHEN type is unknown THEN falls back to the raw string + generic icon", () => {
    const meta = getIntegrationTypeMeta("carrier_pigeon");
    expect(meta.label).toBe("carrier_pigeon");
    expect(meta.icon).toBeDefined();
  });
});

describe("getChannelLinkConfig (channel-link-wiring-task-link-code-card-1 unit-1 / channel-link-deep-links REQ-001)", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    process.env.NEXT_PUBLIC_API_URL = "http://backend.test";
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("WHEN backend responds 200 THEN resolves to {telegram_bot_username, whatsapp_business_number} via apiFetch", async () => {
    const payload = {
      telegram_bot_username: "jeff_ai_bot",
      whatsapp_business_number: "5511999999999",
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify(payload), { status: 200 }));
    global.fetch = fetchMock;

    const result = await getChannelLinkConfig();

    expect(result).toEqual(payload);
    const [url, options] = fetchMock.mock.calls[0];
    expect(String(url)).toContain("/api/integrations/channel-config");
    expect(options).toMatchObject({ credentials: "include" });
  });
});

describe("buildDeepLinkHref (channel-link-wiring-task-link-code-card-1 / add-integration-modal REQ-002)", () => {
  it("WHEN type is telegram and telegram_bot_username is set THEN returns the t.me href", () => {
    const href = buildDeepLinkHref("telegram", "ABC123", {
      telegram_bot_username: "jeff_ai_bot",
      whatsapp_business_number: null,
    });
    expect(href).toBe("https://t.me/jeff_ai_bot?start=ABC123");
  });

  it("WHEN type is whatsapp and whatsapp_business_number is set THEN returns the wa.me href", () => {
    const href = buildDeepLinkHref("whatsapp", "ABC123", {
      telegram_bot_username: null,
      whatsapp_business_number: "5511999999999",
    });
    expect(href).toBe("https://wa.me/5511999999999?text=ABC123");
  });

  it("WHEN the relevant config value is missing THEN returns undefined", () => {
    expect(
      buildDeepLinkHref("telegram", "ABC123", {
        telegram_bot_username: null,
        whatsapp_business_number: "5511999999999",
      })
    ).toBeUndefined();
    expect(
      buildDeepLinkHref("whatsapp", "ABC123", {
        telegram_bot_username: "jeff_ai_bot",
        whatsapp_business_number: null,
      })
    ).toBeUndefined();
  });
});
