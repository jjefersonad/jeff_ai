import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { AssistantButton } from "./AssistantButton";

const mockListAgentProfiles = vi.fn();
const mockSaveConfig = vi.fn();

vi.mock("@/lib/agent-profiles", () => ({
  listAgentProfiles: (...args: unknown[]) => mockListAgentProfiles(...args),
}));

vi.mock("@/lib/config", async () => {
  const actual = await vi.importActual<typeof import("@/lib/config")>(
    "@/lib/config"
  );
  return {
    ...actual,
    saveConfig: (...args: unknown[]) => mockSaveConfig(...args),
  };
});

function profileFor(id: string, name: string) {
  return {
    id,
    user_id: "alice",
    name,
    slug: id,
    system_prompt: "prompt",
    skills_allowlist: null,
    tools_allowlist: null,
    mcp_allowlist: null,
    tier: 1,
    model_override: null,
    is_active: true,
    archived_at: null,
    created_at: "2026-08-19T00:00:00Z",
    updated_at: "2026-08-19T00:00:00Z",
  };
}

describe("AssistantButton — select profile (ui-2 unit-1 / REQ-002)", () => {
  beforeEach(() => {
    mockListAgentProfiles.mockReset();
    mockSaveConfig.mockReset();
  });

  it("WHEN the user picks a profile THEN profileId is saved and assistantId stays unified", async () => {
    mockListAgentProfiles.mockResolvedValue([
      profileFor("profile-marketing", "Assistente de marketing"),
    ]);
    const user = userEvent.setup();

    render(<AssistantButton assistantId="unified" />);

    await user.click(screen.getByRole("button", { name: /agente|assistant/i }));

    const dialog = await screen.findByRole("dialog");
    expect(
      await within(dialog).findByText("Assistente de marketing")
    ).toBeInTheDocument();
    expect(within(dialog).queryByText("Unified")).not.toBeInTheDocument();

    await user.click(
      within(dialog).getByRole("option", { name: /assistente de marketing/i })
    );

    expect(mockSaveConfig).toHaveBeenCalledWith({
      assistantId: "unified",
      profileId: "profile-marketing",
    });
  });

  it("WHEN the user picks Agente padrão THEN profileId is cleared and assistantId stays unified", async () => {
    mockListAgentProfiles.mockResolvedValue([
      profileFor("profile-marketing", "Assistente de marketing"),
    ]);
    const user = userEvent.setup();

    render(
      <AssistantButton assistantId="unified" profileId="profile-marketing" />
    );

    await user.click(screen.getByRole("button", { name: /agente|assistant/i }));

    const dialog = await screen.findByRole("dialog");
    await user.click(
      within(dialog).getByRole("option", { name: /agente padrão|padrão unified/i })
    );

    expect(mockSaveConfig).toHaveBeenCalledWith({ assistantId: "unified" });
    expect(mockSaveConfig.mock.calls[0][0]).not.toHaveProperty("profileId");
  });
});

describe("AssistantButton — empty profile list (ui-2 unit-2 / REQ-002)", () => {
  beforeEach(() => {
    mockListAgentProfiles.mockReset();
    mockSaveConfig.mockReset();
  });

  it("WHEN GET /api/agent-profiles returns [] THEN the modal has no fabricated profile option", async () => {
    mockListAgentProfiles.mockResolvedValue([]);
    const user = userEvent.setup();

    render(<AssistantButton assistantId="unified" />);

    await user.click(screen.getByRole("button", { name: /agente|assistant/i }));

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).queryByRole("option")).not.toBeInTheDocument();
    expect(within(dialog).queryByText("Unified")).not.toBeInTheDocument();
    expect(mockSaveConfig).not.toHaveBeenCalled();
  });
});
