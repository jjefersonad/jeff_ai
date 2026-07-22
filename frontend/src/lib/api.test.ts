import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { ApiError, setUnauthorizedHandler, uploadAttachment } from "./api";

describe("uploadAttachment (chat-file-attachment REQ-002)", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    process.env.NEXT_PUBLIC_API_URL = "http://backend.test";
  });

  afterEach(() => {
    global.fetch = originalFetch;
    setUnauthorizedHandler(null);
  });

  it("REQ-002: uploads through apiFetch with credentials included and multipart body", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          attachment_id: "att-1",
          url: "/api/attachments/att-1",
          metadata: {
            thread_id: "t1",
            filename: "report.pdf",
            content_type: "application/pdf",
            size_bytes: 4,
          },
        }),
        { status: 200 }
      )
    );
    global.fetch = fetchMock;

    const file = new File(["data"], "report.pdf", { type: "application/pdf" });
    const result = await uploadAttachment(file, "t1");

    expect(result.attachment_id).toBe("att-1");
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://backend.test/api/attachments");
    expect(init.credentials).toBe("include");
    expect(init.body).toBeInstanceOf(FormData);
  });

  it("REQ-002: does not force a JSON Content-Type header, letting the browser set the multipart boundary", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("{}", { status: 200 }));
    global.fetch = fetchMock;

    await uploadAttachment(new File(["data"], "report.pdf"), "t1").catch(() => {});

    const [, init] = fetchMock.mock.calls[0];
    const headers = init.headers as Record<string, string>;
    expect(headers["Content-Type"]).toBeUndefined();
  });

  it("REQ-002: a 401 response triggers the re-authentication handler and rejects instead of resolving", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: "Unauthorized" }), { status: 401 })
    );
    global.fetch = fetchMock;
    const unauthorizedSpy = vi.fn();
    setUnauthorizedHandler(unauthorizedSpy);

    const file = new File(["data"], "report.pdf");
    await expect(uploadAttachment(file, "t1")).rejects.toThrow(ApiError);

    expect(unauthorizedSpy).toHaveBeenCalledTimes(1);
  });
});
