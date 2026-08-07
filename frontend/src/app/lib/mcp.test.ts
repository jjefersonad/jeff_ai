import { describe, it, expect, vi, afterEach } from "vitest";
import { createServer, updateServer } from "./mcp";

describe("user-scoped-mcp-config-storage-task-frontend-1, REQ-004", () => {
  const originalFetch = global.fetch;

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("http transport payload (POST): fetch body includes transport, url and headers (accepts arbitrary header names)", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response("{}", { status: 201 })
    );
    global.fetch = fetchMock;

    await createServer("zernio", {
      transport: "http",
      url: "https://mcp.zernio.example/mcp",
      headers: { Authorization: "Bearer ${ZERNIO_TOKEN}" },
    });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/mcp/servers");
    expect(init.method).toBe("POST");
    expect(init.credentials).toBe("include");
    expect(JSON.parse(init.body as string)).toEqual({
      name: "zernio",
      transport: "http",
      url: "https://mcp.zernio.example/mcp",
      headers: { Authorization: "Bearer ${ZERNIO_TOKEN}" },
    });
  });

  it("http transport payload (PUT): fetch body includes transport, url and headers (name NOT in body — rides in URL)", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response("{}", { status: 200 })
    );
    global.fetch = fetchMock;

    await updateServer("zernio", {
      transport: "http",
      url: "https://mcp.zernio.example/mcp",
      headers: { Authorization: "Bearer ${ZERNIO_TOKEN}" },
    });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/mcp/servers/zernio");
    expect(init.method).toBe("PUT");
    // Body must NOT re-include `name` (it rides in the URL path)
    const body = JSON.parse(init.body as string);
    expect(body).not.toHaveProperty("name");
    expect(body).toEqual({
      transport: "http",
      url: "https://mcp.zernio.example/mcp",
      headers: { Authorization: "Bearer ${ZERNIO_TOKEN}" },
    });
  });

  it("stdio payload shape (POST) is unchanged from today's behavior", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response("{}", { status: 201 })
    );
    global.fetch = fetchMock;

    await createServer("my-stdio-server", {
      transport: "stdio",
      command: "npx",
      args: ["-y", "@modelcontextprotocol/server-example"],
      env: { API_KEY: "MY_STDIO_API_KEY" },
    });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(init.body as string)).toEqual({
      name: "my-stdio-server",
      transport: "stdio",
      command: "npx",
      args: ["-y", "@modelcontextprotocol/server-example"],
      env: { API_KEY: "MY_STDIO_API_KEY" },
    });
  });

  it("stdio payload shape (PUT) is unchanged from today's behavior", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response("{}", { status: 200 })
    );
    global.fetch = fetchMock;

    await updateServer("my-stdio-server", {
      transport: "stdio",
      command: "npx",
      args: ["-y", "@modelcontextprotocol/server-example"],
      env: { API_KEY: "MY_STDIO_API_KEY" },
    });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    const body = JSON.parse(init.body as string);
    expect(body).not.toHaveProperty("name");
    expect(body).toEqual({
      transport: "stdio",
      command: "npx",
      args: ["-y", "@modelcontextprotocol/server-example"],
      env: { API_KEY: "MY_STDIO_API_KEY" },
    });
  });
});
