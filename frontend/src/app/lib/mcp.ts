/**
 * Types and fetch helpers for the MCP server admin UI
 * (task `unified-agent-realignment-task-mcp-3`).
 *
 * All requests go through the Next.js rewrite `/api/mcp/*` →
 * `image-server:8080/api/mcp/*` (see `next.config.ts`). That process is
 * separate from the agent graph — the admin API it exposes is never
 * reachable by any agent tool (REQ-001 of `mcp-client`: the agent cannot
 * self-configure servers).
 *
 * Note: these calls do NOT go through the `AuthProvider`'s 401 interceptor
 * (the MCP admin server is intentionally a separate process, outside the
 * Jeff AI backend's auth surface — see Open Question in the design doc).
 * We still set `credentials: 'include'` so the httpOnly session cookie
 * travels if the MCP admin process ever needs it in the future; the cookie
 * is just ignored today.
 */

export interface McpServerSummary {
  name: string;
  command: string;
  args: string[];
  /** key -> env var NAME (never the resolved secret value, see REQ-007). */
  env: Record<string, string>;
  status: "connected" | "offline" | "error";
  message: string | null;
  tool_count: number;
}

export interface McpToolInfo {
  name: string;
  qualified_name: string;
  description: string;
  capability: string;
}

async function parseErrorDetail(res: Response): Promise<string> {
  try {
    const data = await res.json();
    return data?.detail || res.statusText;
  } catch {
    return res.statusText;
  }
}

const MCP_FETCH_INIT: RequestInit = {
  credentials: "include",
};

export async function fetchServers(): Promise<McpServerSummary[]> {
  const res = await fetch("/api/mcp/servers", MCP_FETCH_INIT);
  if (!res.ok) throw new Error(await parseErrorDetail(res));
  const data = await res.json();
  return data.servers;
}

export async function fetchServerTools(name: string): Promise<McpToolInfo[]> {
  const res = await fetch(
    `/api/mcp/servers/${encodeURIComponent(name)}/tools`,
    MCP_FETCH_INIT
  );
  if (!res.ok) throw new Error(await parseErrorDetail(res));
  const data = await res.json();
  return data.tools;
}

export async function fetchCapabilities(): Promise<string[]> {
  const res = await fetch("/api/mcp/capabilities", MCP_FETCH_INIT);
  if (!res.ok) throw new Error(await parseErrorDetail(res));
  const data = await res.json();
  return data.capabilities;
}

export interface ServerWritePayload {
  command: string;
  args: string[];
  env: Record<string, string>;
}

export async function createServer(
  name: string,
  payload: ServerWritePayload
): Promise<void> {
  const res = await fetch("/api/mcp/servers", {
    ...MCP_FETCH_INIT,
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, ...payload }),
  });
  if (!res.ok) throw new Error(await parseErrorDetail(res));
}

export async function updateServer(
  name: string,
  payload: ServerWritePayload
): Promise<void> {
  const res = await fetch(`/api/mcp/servers/${encodeURIComponent(name)}`, {
    ...MCP_FETCH_INIT,
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await parseErrorDetail(res));
}

export async function deleteServer(name: string): Promise<void> {
  const res = await fetch(`/api/mcp/servers/${encodeURIComponent(name)}`, {
    ...MCP_FETCH_INIT,
    method: "DELETE",
  });
  if (!res.ok && res.status !== 204) throw new Error(await parseErrorDetail(res));
}

export async function setToolCapability(
  toolName: string,
  capability: string
): Promise<void> {
  const res = await fetch("/api/mcp/tools/capability", {
    ...MCP_FETCH_INIT,
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ tool_name: toolName, capability }),
  });
  if (!res.ok) throw new Error(await parseErrorDetail(res));
}

export async function clearToolCapability(toolName: string): Promise<void> {
  const res = await fetch(
    `/api/mcp/tools/capability/${encodeURIComponent(toolName)}`,
    { ...MCP_FETCH_INIT, method: "DELETE" }
  );
  if (!res.ok) throw new Error(await parseErrorDetail(res));
}
