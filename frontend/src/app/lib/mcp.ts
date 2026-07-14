/**
 * Types and fetch helpers for the MCP server admin UI
 * (task `unified-agent-realignment-task-mcp-3`).
 *
 * All requests go through the Next.js rewrite `/api/mcp/*` →
 * `image-server:8080/api/mcp/*` (see `next.config.ts`). That process is
 * separate from the agent graph — the admin API it exposes is never
 * reachable by any agent tool (REQ-001 of `mcp-client`: the agent cannot
 * self-configure servers).
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

export async function fetchServers(): Promise<McpServerSummary[]> {
  const res = await fetch("/api/mcp/servers");
  if (!res.ok) throw new Error(await parseErrorDetail(res));
  const data = await res.json();
  return data.servers;
}

export async function fetchServerTools(name: string): Promise<McpToolInfo[]> {
  const res = await fetch(`/api/mcp/servers/${encodeURIComponent(name)}/tools`);
  if (!res.ok) throw new Error(await parseErrorDetail(res));
  const data = await res.json();
  return data.tools;
}

export async function fetchCapabilities(): Promise<string[]> {
  const res = await fetch("/api/mcp/capabilities");
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
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await parseErrorDetail(res));
}

export async function deleteServer(name: string): Promise<void> {
  const res = await fetch(`/api/mcp/servers/${encodeURIComponent(name)}`, {
    method: "DELETE",
  });
  if (!res.ok && res.status !== 204) throw new Error(await parseErrorDetail(res));
}

export async function setToolCapability(
  toolName: string,
  capability: string
): Promise<void> {
  const res = await fetch("/api/mcp/tools/capability", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ tool_name: toolName, capability }),
  });
  if (!res.ok) throw new Error(await parseErrorDetail(res));
}

export async function clearToolCapability(toolName: string): Promise<void> {
  const res = await fetch(
    `/api/mcp/tools/capability/${encodeURIComponent(toolName)}`,
    { method: "DELETE" }
  );
  if (!res.ok) throw new Error(await parseErrorDetail(res));
}
