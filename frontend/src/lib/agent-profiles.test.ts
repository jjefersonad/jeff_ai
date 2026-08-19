import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

import { ApiError, setUnauthorizedHandler } from "./api";
import { archiveAgentProfile, createAgentProfile, listAgentProfiles, updateAgentProfile } from "./agent-profiles";

const sampleProfile = {
  id: "profile-1",
  user_id: "alice",
  name: "Assistente de marketing",
  slug: "marketing",
  system_prompt: "Você é o agente de marketing.",
  skills_allowlist: ["brand-guidelines"],
  tools_allowlist: ["web_search"],
  mcp_allowlist: ["gmail"],
  tier: 2,
  model_override: null,
  is_active: true,
  archived_at: null,
  created_at: "2026-08-19T00:00:00Z",
  updated_at: "2026-08-19T00:00:00Z",
};

describe("agent-profiles.ts (ui-1 / REQ-001)", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    process.env.NEXT_PUBLIC_API_URL = "http://backend.test";
  });

  afterEach(() => {
    global.fetch = originalFetch;
    setUnauthorizedHandler(null);
  });

  it("listAgentProfiles() calls GET /api/agent-profiles with credentials and returns the parsed list", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        new Response(JSON.stringify([sampleProfile]), { status: 200 })
      );
    global.fetch = fetchMock;

    const result = await listAgentProfiles();

    expect(result).toEqual([sampleProfile]);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://backend.test/api/agent-profiles");
    expect(init.credentials).toBe("include");
  });

  it("archiveAgentProfile(id) calls POST /api/agent-profiles/{id}/archive and never DELETE", async () => {
    const archived = { ...sampleProfile, archived_at: "2026-08-19T12:00:00Z" };
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify(archived), { status: 200 }));
    global.fetch = fetchMock;

    const result = await archiveAgentProfile(sampleProfile.id);

    expect(result).toEqual(archived);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(
      `http://backend.test/api/agent-profiles/${sampleProfile.id}/archive`
    );
    expect(init.method).toBe("POST");
    expect(init.credentials).toBe("include");
    expect(String(url)).not.toMatch(/DELETE/i);
    expect(init.method).not.toBe("DELETE");
  });

  it("createAgentProfile() POSTs name, slug, prompt, allowlists, tier and model_override to /api/agent-profiles", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        new Response(JSON.stringify(sampleProfile), { status: 201 })
      );
    global.fetch = fetchMock;

    const payload = {
      name: sampleProfile.name,
      slug: sampleProfile.slug,
      system_prompt: sampleProfile.system_prompt,
      skills_allowlist: sampleProfile.skills_allowlist,
      tools_allowlist: sampleProfile.tools_allowlist,
      mcp_allowlist: sampleProfile.mcp_allowlist,
      tier: sampleProfile.tier,
      model_override: null as string | null,
    };

    const result = await createAgentProfile(payload);

    expect(result).toEqual(sampleProfile);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://backend.test/api/agent-profiles");
    expect(init.method).toBe("POST");
    expect(init.credentials).toBe("include");
    expect(JSON.parse(init.body as string)).toEqual(payload);
  });

  it("updateAgentProfile(id) PATCHes allowlists without slug", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        new Response(JSON.stringify(sampleProfile), { status: 200 })
      );
    global.fetch = fetchMock;

    const payload = {
      name: sampleProfile.name,
      system_prompt: sampleProfile.system_prompt,
      skills_allowlist: ["brand-guidelines"],
      tools_allowlist: ["web_search"],
      mcp_allowlist: ["gmail"],
      tier: 2,
      model_override: null as string | null,
    };

    await updateAgentProfile(sampleProfile.id, payload);

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(
      `http://backend.test/api/agent-profiles/${sampleProfile.id}`
    );
    expect(init.method).toBe("PATCH");
    const body = JSON.parse(init.body as string) as Record<string, unknown>;
    expect(body).toEqual(payload);
    expect(body).not.toHaveProperty("slug");
  });

  it("WHEN backend responds non-2xx THEN throws ApiError", async () => {
    global.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: "Unauthorized" }), { status: 401 })
    );

    const error = await listAgentProfiles().catch((err: unknown) => err);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 401, message: "Unauthorized" });
  });
});
