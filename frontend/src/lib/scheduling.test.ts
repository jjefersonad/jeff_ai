import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { ApiError, setUnauthorizedHandler } from "./api";
import {
  listScheduledTasks,
  listDeliveryChannels,
  createScheduledTask,
  updateScheduledTask,
  cancelScheduledTask,
} from "./scheduling";

const sampleTask = {
  id: "task-1",
  prompt: "Summarize inbox",
  thread_id: "thread-1",
  schedule_kind: "cron",
  schedule_expr: "0 9 * * *",
  tool_scope: "restricted",
  skills: [],
  timeout_seconds: 300,
  status: "scheduled",
  owner_user_key: "web:user-1",
  delivery_user_key: null,
  started_at: null,
  finished_at: null,
  error: null,
  notify_status: null,
  notify_error: null,
  created_at: "2026-07-28T00:00:00Z",
  profile_id: null,
};

describe("scheduling.ts", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    process.env.NEXT_PUBLIC_API_URL = "http://backend.test";
  });

  afterEach(() => {
    global.fetch = originalFetch;
    setUnauthorizedHandler(null);
  });

  it("listScheduledTasks() calls GET /api/scheduled-tasks with credentials and returns the parsed list", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify([sampleTask]), { status: 200 }));
    global.fetch = fetchMock;

    const result = await listScheduledTasks();

    expect(result).toEqual([sampleTask]);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://backend.test/api/scheduled-tasks");
    expect(init.credentials).toBe("include");
  });

  it("listDeliveryChannels() calls GET /api/scheduling/delivery-channels", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ channels: ["web", "whatsapp"] }), { status: 200 })
    );
    global.fetch = fetchMock;

    const result = await listDeliveryChannels();

    expect(result).toEqual(["web", "whatsapp"]);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://backend.test/api/scheduling/delivery-channels");
    expect(init.credentials).toBe("include");
  });

  it("createScheduledTask(payload) calls POST /api/scheduled-tasks with the payload as JSON body and returns the created task", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify(sampleTask), { status: 201 }));
    global.fetch = fetchMock;

    const payload = {
      prompt: "Summarize inbox",
      schedule_kind: "cron",
      schedule_expr: "0 9 * * *",
    };
    const result = await createScheduledTask(payload);

    expect(result).toEqual(sampleTask);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://backend.test/api/scheduled-tasks");
    expect(init.method).toBe("POST");
    expect(init.credentials).toBe("include");
    expect(JSON.parse(init.body as string)).toEqual(payload);
  });

  it("ui-1 unit-1: createScheduledTask includes delivery_channel when selected", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          ...sampleTask,
          delivery_user_key: "telegram:42",
        }),
        { status: 201 }
      )
    );
    global.fetch = fetchMock;

    const payload = {
      prompt: "Notify me",
      schedule_kind: "once",
      schedule_expr: "2026-12-31T23:59:00",
      delivery_channel: "telegram",
    };
    await createScheduledTask(payload);

    const [, init] = fetchMock.mock.calls[0];
    expect(JSON.parse(init.body as string)).toEqual(payload);
  });

  it("updateScheduledTask(id, payload) calls PATCH /api/scheduled-tasks/{id} with the payload as JSON body", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify(sampleTask), { status: 200 }));
    global.fetch = fetchMock;

    const payload = { prompt: "New prompt" };
    const result = await updateScheduledTask("task-1", payload);

    expect(result).toEqual(sampleTask);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://backend.test/api/scheduled-tasks/task-1");
    expect(init.method).toBe("PATCH");
    expect(init.credentials).toBe("include");
    expect(JSON.parse(init.body as string)).toEqual(payload);
  });

  it("cancelScheduledTask(id) calls DELETE /api/scheduled-tasks/{id} with credentials", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    global.fetch = fetchMock;

    await cancelScheduledTask("task-1");

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://backend.test/api/scheduled-tasks/task-1");
    expect(init.method).toBe("DELETE");
    expect(init.credentials).toBe("include");
  });

  it("throws ApiError on non-OK response for all four functions", async () => {
    global.fetch = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify({ detail: "Forbidden" }), { status: 403 }));

    await expect(listScheduledTasks()).rejects.toThrow(ApiError);
    await expect(
      createScheduledTask({ prompt: "x", schedule_kind: "cron", schedule_expr: "* * * * *" })
    ).rejects.toThrow(ApiError);
    await expect(updateScheduledTask("task-1", { prompt: "x" })).rejects.toThrow(ApiError);
    await expect(cancelScheduledTask("task-1")).rejects.toThrow(ApiError);
  });
});
