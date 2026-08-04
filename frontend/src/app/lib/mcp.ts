/**
 * Types and fetch helpers for the MCP server admin UI
 * (task `unified-agent-realignment-task-mcp-3`).
 *
 * All requests go through the Next.js rewrite `/api/mcp/*` → the backend
 * (`BACKEND_INTERNAL_URL`, see `next.config.ts`) — same process as the
 * agent graph since `retire-image-server` retired the separate
 * `image-server` container. The admin API is still never reachable by any
 * agent tool (REQ-001/REQ-008 of `mcp-client`): that guarantee now comes
 * from `require_auth` (no agent tool has the browser's session cookie),
 * not process isolation.
 *
 * Note: these calls do NOT go through the `AuthProvider`'s 401 interceptor
 * — they use a bare `fetch`, not `apiFetch`. A 401 here (e.g. expired
 * session while the MCP admin dialog is open) surfaces as a thrown `Error`
 * to the caller instead of redirecting to `/public/login`. Wiring this
 * into the shared interceptor is a reasonable follow-up, not done here.
 * We set `credentials: 'include'` so the httpOnly session cookie travels
 * with every request, same as `apiFetch`.
 */

export interface McpServerSummary {
  name: string;
  transport: "stdio" | "http";
  command: string;
  args: string[];
  url: string;
  /** key -> env var NAME (never the resolved secret value, see REQ-007). */
  env: Record<string, string>;
  /** key -> var NAME or `***` (never the resolved secret value). */
  headers: Record<string, string>;
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

/**
 * Body of `POST /api/mcp/servers` and `PUT /api/mcp/servers/{name}`.
 *
 * Discriminated by `transport` — every variant carries ONLY the fields
 * its transport actually uses. Mirrors the backend's `ServerWriteRequest`
 * (see `mcp_admin_api.py`) and `user-mcp-server-store` (table
 * `user_mcp_servers`).
 *
 * - `stdio` (`REQ-004` of `user-scoped-mcp-config-storage`, proposal Impact):
 *   a local process spawned via `command` + `args`; `env` maps each server
 *   key to an env var NAME (the resolved secret never crosses the wire —
 *   see REQ-007).
 * - `http`: a remote MCP endpoint at `url`; `headers` is the same
 *   `${VAR}` reference convention as `env` — values are stored encrypted
 *   server-side, never sent in plaintext over the form. This is the shape
 *   Zernio needs; it was previously hand-edited into `mcp_servers.json`,
 *   which the rest of this change retires.
 */
export type ServerWritePayload =
  | {
      transport: "stdio";
      command: string;
      args: string[];
      env: Record<string, string>;
    }
  | {
      transport: "http";
      url: string;
      headers: Record<string, string>;
    };

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
