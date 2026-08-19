import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import AgentProfilesPage from "./page";

const mockListAgentProfiles = vi.fn();
const mockCreateAgentProfile = vi.fn();
const mockUpdateAgentProfile = vi.fn();
const mockArchiveAgentProfile = vi.fn();

vi.mock("@/lib/agent-profiles", () => ({
  listAgentProfiles: (...args: unknown[]) => mockListAgentProfiles(...args),
  createAgentProfile: (...args: unknown[]) => mockCreateAgentProfile(...args),
  updateAgentProfile: (...args: unknown[]) => mockUpdateAgentProfile(...args),
  archiveAgentProfile: (...args: unknown[]) => mockArchiveAgentProfile(...args),
}));

function profileFor(
  id: string,
  extras: Record<string, unknown> = {}
) {
  return {
    id,
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
    ...extras,
  };
}

describe("AgentProfilesPage — list and archive (ui-1 unit-1 / REQ-001)", () => {
  beforeEach(() => {
    mockListAgentProfiles.mockReset();
    mockCreateAgentProfile.mockReset();
    mockUpdateAgentProfile.mockReset();
    mockArchiveAgentProfile.mockReset();
  });

  it("WHEN the user opens /agent-profiles THEN GET results render and another user's profiles do not", async () => {
    mockListAgentProfiles.mockResolvedValue([
      profileFor("profile-1", { name: "Assistente de marketing" }),
    ]);

    render(<AgentProfilesPage />);

    expect(await screen.findByText("Assistente de marketing")).toBeInTheDocument();
    expect(screen.queryByText("Perfil do Bob")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /excluir/i })).not.toBeInTheDocument();
  });

  it("WHEN the user archives a profile THEN POST /{id}/archive is called and the row leaves the list", async () => {
    const mine = profileFor("profile-1");
    mockListAgentProfiles.mockResolvedValue([mine]);
    mockArchiveAgentProfile.mockResolvedValue({
      ...mine,
      archived_at: "2026-08-19T12:00:00Z",
    });
    const user = userEvent.setup();

    render(<AgentProfilesPage />);

    await screen.findByText(mine.name);
    await user.click(screen.getByRole("button", { name: /arquivar/i }));

    const dialog = screen.getByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: /confirmar/i }));

    expect(mockArchiveAgentProfile).toHaveBeenCalledWith(mine.id);
    expect(screen.queryByText(mine.name)).not.toBeInTheDocument();
  });
});

describe("AgentProfilesPage — create allowlists (ui-1 unit-2 / REQ-001)", () => {
  beforeEach(() => {
    mockListAgentProfiles.mockReset();
    mockCreateAgentProfile.mockReset();
    mockUpdateAgentProfile.mockReset();
    mockArchiveAgentProfile.mockReset();
    mockListAgentProfiles.mockResolvedValue([]);
  });

  it("WHEN the user submits a new profile with skills/tools/MCP allowlists THEN the client POSTs those fields", async () => {
    const created = profileFor("profile-new", {
      name: "Pesquisa",
      slug: "pesquisa",
      system_prompt: "Você pesquisa.",
      skills_allowlist: ["arxiv-search"],
      tools_allowlist: ["web_search"],
      mcp_allowlist: ["gmail"],
      tier: 1,
    });
    mockCreateAgentProfile.mockResolvedValue(created);
    const user = userEvent.setup();

    render(<AgentProfilesPage />);

    await user.click(await screen.findByRole("button", { name: /novo perfil/i }));

    const dialog = await screen.findByRole("dialog");
    await user.type(within(dialog).getByLabelText(/^nome$/i), created.name);
    await user.type(within(dialog).getByLabelText(/^slug$/i), created.slug);
    await user.type(
      within(dialog).getByLabelText(/prompt do sistema/i),
      created.system_prompt
    );
    await user.type(within(dialog).getByLabelText(/skills/i), "arxiv-search");
    await user.type(within(dialog).getByLabelText(/ferramentas/i), "web_search");
    await user.type(within(dialog).getByLabelText(/^mcp$/i), "gmail");
    await user.click(within(dialog).getByRole("button", { name: /salvar/i }));

    expect(mockCreateAgentProfile).toHaveBeenCalledWith(
      expect.objectContaining({
        name: created.name,
        slug: created.slug,
        system_prompt: created.system_prompt,
        skills_allowlist: ["arxiv-search"],
        tools_allowlist: ["web_search"],
        mcp_allowlist: ["gmail"],
      })
    );
    expect(await screen.findByText(created.name)).toBeInTheDocument();
  });

  it("WHEN the user edits a profile THEN PATCH is sent with allowlists and without slug", async () => {
    const existing = profileFor("profile-1");
    const updated = {
      ...existing,
      name: "Pesquisa",
      skills_allowlist: ["arxiv-search"],
      tools_allowlist: ["web_search"],
      mcp_allowlist: ["gmail"],
    };
    mockListAgentProfiles.mockResolvedValue([existing]);
    mockUpdateAgentProfile.mockResolvedValue(updated);
    const user = userEvent.setup();

    render(<AgentProfilesPage />);

    await screen.findByText(existing.name);
    await user.click(screen.getByRole("button", { name: /editar/i }));

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).queryByLabelText(/^slug$/i)).not.toBeInTheDocument();

    const nameInput = within(dialog).getByLabelText(/^nome$/i);
    await user.clear(nameInput);
    await user.type(nameInput, updated.name);

    const skillsInput = within(dialog).getByLabelText(/skills/i);
    await user.clear(skillsInput);
    await user.type(skillsInput, "arxiv-search");

    const toolsInput = within(dialog).getByLabelText(/ferramentas/i);
    await user.clear(toolsInput);
    await user.type(toolsInput, "web_search");

    const mcpInput = within(dialog).getByLabelText(/^mcp$/i);
    await user.clear(mcpInput);
    await user.type(mcpInput, "gmail");

    await user.click(within(dialog).getByRole("button", { name: /salvar/i }));

    expect(mockUpdateAgentProfile).toHaveBeenCalledWith(
      existing.id,
      expect.objectContaining({
        name: updated.name,
        skills_allowlist: ["arxiv-search"],
        tools_allowlist: ["web_search"],
        mcp_allowlist: ["gmail"],
      })
    );
    expect(mockUpdateAgentProfile.mock.calls[0][1]).not.toHaveProperty("slug");
    expect(await screen.findByText(updated.name)).toBeInTheDocument();
  });
});
