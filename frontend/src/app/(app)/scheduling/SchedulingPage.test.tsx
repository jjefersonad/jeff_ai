import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, within, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import SchedulingPage from "./page";

const mockListScheduledTasks = vi.fn();
const mockListDeliveryChannels = vi.fn();
const mockCreateScheduledTask = vi.fn();
const mockUpdateScheduledTask = vi.fn();
const mockCancelScheduledTask = vi.fn();

vi.mock("@/lib/scheduling", async () => {
  const actual = await vi.importActual<typeof import("@/lib/scheduling")>(
    "@/lib/scheduling"
  );
  return {
    ...actual,
    listScheduledTasks: (...args: unknown[]) => mockListScheduledTasks(...args),
    listDeliveryChannels: (...args: unknown[]) => mockListDeliveryChannels(...args),
    createScheduledTask: (...args: unknown[]) => mockCreateScheduledTask(...args),
    updateScheduledTask: (...args: unknown[]) => mockUpdateScheduledTask(...args),
    cancelScheduledTask: (...args: unknown[]) => mockCancelScheduledTask(...args),
  };
});

const mockListAgentProfiles = vi.fn();
vi.mock("@/lib/agent-profiles", () => ({
  listAgentProfiles: (...args: unknown[]) => mockListAgentProfiles(...args),
}));

const mockGetConfig = vi.fn();
vi.mock("@/lib/config", async () => {
  const actual = await vi.importActual<typeof import("@/lib/config")>(
    "@/lib/config"
  );
  return {
    ...actual,
    getConfig: (...args: unknown[]) => mockGetConfig(...args),
  };
});

const taskFor = (id: string, owner: string, extras: Record<string, unknown> = {}) => ({
  id,
  prompt: `Prompt ${id}`,
  thread_id: `thread-${id}`,
  schedule_kind: "cron",
  schedule_expr: "0 9 * * *",
  tool_scope: "restricted",
  skills: [],
  timeout_seconds: 300,
  status: "scheduled",
  owner_user_key: owner,
  delivery_user_key: null,
  started_at: null,
  finished_at: null,
  error: null,
  notify_status: null,
  notify_error: null,
  created_at: "2026-07-28T00:00:00Z",
  profile_id: null,
  ...extras,
});

beforeEach(() => {
  mockListAgentProfiles.mockReset();
  mockListAgentProfiles.mockResolvedValue([]);
  mockGetConfig.mockReset();
  mockGetConfig.mockReturnValue({ assistantId: "unified" });
});

describe("SchedulingPage (frontend-page-1 unit-1/unit-2 / REQ-001)", () => {
  beforeEach(() => {
    mockListScheduledTasks.mockReset();
    mockListDeliveryChannels.mockReset();
    mockCreateScheduledTask.mockReset();
    mockListDeliveryChannels.mockResolvedValue(["web"]);
  });

  it("unit-1: WHEN listScheduledTasks() resolves N tasks THEN the page renders N entries matching them", async () => {
    const tasks = [taskFor("task-1", "web:alice"), taskFor("task-2", "web:alice"), taskFor("task-3", "web:alice")];
    mockListScheduledTasks.mockResolvedValue(tasks);

    render(<SchedulingPage />);

    for (const task of tasks) {
      expect(await screen.findByText(task.prompt)).toBeInTheDocument();
    }
    expect(screen.getAllByRole("listitem")).toHaveLength(tasks.length);
  });

  it("unit-2: renders exactly the set returned regardless of owner_user_key — no client-side filtering", async () => {
    const tasks = [
      taskFor("task-1", "web:alice"),
      taskFor("task-2", "web:bob"),
      taskFor("task-3", "web:carol"),
    ];
    mockListScheduledTasks.mockResolvedValue(tasks);

    render(<SchedulingPage />);

    for (const task of tasks) {
      expect(await screen.findByText(task.prompt)).toBeInTheDocument();
    }
    expect(screen.getAllByRole("listitem")).toHaveLength(tasks.length);
  });
});

describe("SchedulingPage — create form (frontend-page-2 unit-1 / REQ-002)", () => {
  beforeEach(() => {
    mockListScheduledTasks.mockReset();
    mockListDeliveryChannels.mockReset();
    mockCreateScheduledTask.mockReset();
    mockListScheduledTasks.mockResolvedValue([]);
    mockListDeliveryChannels.mockResolvedValue(["web"]);
  });

  it("unit-1: WHEN the user submits the create form with valid fields THEN createScheduledTask is called and the returned task is appended to the list without a full reload", async () => {
    const created = taskFor("task-new", "web:alice");
    mockCreateScheduledTask.mockResolvedValue(created);
    const user = userEvent.setup();

    render(<SchedulingPage />);

    await user.type(screen.getByLabelText(/prompt/i), created.prompt);
    await user.type(screen.getByLabelText(/expressão/i), "0 9 * * *");
    await user.click(screen.getByRole("button", { name: /criar/i }));

    expect(mockCreateScheduledTask).toHaveBeenCalledWith(
      expect.objectContaining({
        prompt: created.prompt,
        schedule_kind: "cron",
        schedule_expr: "0 9 * * *",
        delivery_channel: "web",
      })
    );
    expect(await screen.findByText(created.prompt)).toBeInTheDocument();
  });
});

describe("SchedulingPage — delivery destination (ui-1)", () => {
  beforeEach(() => {
    mockListScheduledTasks.mockReset();
    mockListDeliveryChannels.mockReset();
    mockCreateScheduledTask.mockReset();
    mockListScheduledTasks.mockResolvedValue([]);
  });

  it("unit-2: WHEN delivery-channels returns web and whatsapp THEN the selector exposes those options", async () => {
    mockListDeliveryChannels.mockResolvedValue(["web", "whatsapp"]);
    const user = userEvent.setup();

    render(<SchedulingPage />);

    await screen.findByLabelText(/destino de entrega/i);
    await user.click(screen.getByLabelText(/destino de entrega/i));

    expect(await screen.findByRole("option", { name: "Web" })).toBeInTheDocument();
    expect(await screen.findByRole("option", { name: "WhatsApp" })).toBeInTheDocument();
  });

  it("unit-1: WHEN telegram is selected THEN createScheduledTask is called with delivery_channel telegram", async () => {
    mockListDeliveryChannels.mockResolvedValue(["web", "telegram"]);
    mockCreateScheduledTask.mockResolvedValue(
      taskFor("task-tg", "web:alice", {
        delivery_user_key: "telegram:42",
        prompt: "mande no telegram",
      })
    );
    const user = userEvent.setup();

    render(<SchedulingPage />);

    await screen.findByLabelText(/destino de entrega/i);
    await user.click(screen.getByLabelText(/destino de entrega/i));
    await user.click(await screen.findByRole("option", { name: "Telegram" }));

    await user.type(screen.getByLabelText(/^prompt$/i), "mande no telegram");
    await user.type(screen.getByLabelText(/expressão/i), "0 9 * * *");
    await user.click(screen.getByRole("button", { name: /criar/i }));

    expect(mockCreateScheduledTask).toHaveBeenCalledWith(
      expect.objectContaining({
        delivery_channel: "telegram",
      })
    );
  });

  it("lists show effective destination when delivery_user_key is present", async () => {
    mockListDeliveryChannels.mockResolvedValue(["web", "whatsapp"]);
    mockListScheduledTasks.mockResolvedValue([
      taskFor("task-1", "web:alice", {
        delivery_user_key: "whatsapp:5511999999999",
        prompt: "zap task",
      }),
    ]);

    render(<SchedulingPage />);

    expect(await screen.findByText(/Destino: WhatsApp/)).toBeInTheDocument();
    expect(screen.getByText(/whatsapp:5511999999999/)).toBeInTheDocument();
  });
});

describe("SchedulingPage — edit action (frontend-page-3 / REQ-003)", () => {
  beforeEach(() => {
    mockListScheduledTasks.mockReset();
    mockListDeliveryChannels.mockReset();
    mockCreateScheduledTask.mockReset();
    mockUpdateScheduledTask.mockReset();
    mockListDeliveryChannels.mockResolvedValue(["web"]);
  });

  it("unit-1: WHEN the user submits the edit form for an editable SCHEDULED task THEN updateScheduledTask is called with the changed fields and the list reflects the new values", async () => {
    const task = taskFor("task-1", "web:alice");
    mockListScheduledTasks.mockResolvedValue([task]);
    const updated = { ...task, prompt: "Updated prompt" };
    mockUpdateScheduledTask.mockResolvedValue(updated);
    const user = userEvent.setup();

    render(<SchedulingPage />);

    await screen.findByText(task.prompt);
    await user.click(screen.getByRole("button", { name: /editar/i }));

    const dialog = screen.getByRole("dialog");
    const promptField = within(dialog).getByLabelText(/prompt/i);
    await user.clear(promptField);
    await user.type(promptField, updated.prompt);
    await user.click(within(dialog).getByRole("button", { name: /salvar/i }));

    expect(mockUpdateScheduledTask).toHaveBeenCalledWith(
      task.id,
      expect.objectContaining({ prompt: updated.prompt })
    );
    expect(await screen.findByText(updated.prompt)).toBeInTheDocument();
  });

  it("unit-2: WHEN a rendered task has status RUNNING, SUCCEEDED, or FAILED THEN its edit control is absent or disabled, while a SCHEDULED task's edit control stays enabled", async () => {
    const scheduledTask = taskFor("task-scheduled", "web:alice");
    const nonEditableTasks = [
      { ...taskFor("task-running", "web:alice"), status: "running" },
      { ...taskFor("task-succeeded", "web:alice"), status: "succeeded" },
      { ...taskFor("task-failed", "web:alice"), status: "failed" },
    ];
    mockListScheduledTasks.mockResolvedValue([scheduledTask, ...nonEditableTasks]);

    render(<SchedulingPage />);

    for (const task of [scheduledTask, ...nonEditableTasks]) {
      await screen.findByText(task.prompt);
    }

    const scheduledItem = screen.getByText(scheduledTask.prompt).closest("li")!;
    const enabledEditButton = within(scheduledItem).getByRole("button", {
      name: /editar/i,
    });
    expect(enabledEditButton).toBeEnabled();

    for (const task of nonEditableTasks) {
      const item = screen.getByText(task.prompt).closest("li")!;
      const editButton = within(item).queryByRole("button", { name: /editar/i });
      if (editButton) {
        expect(editButton).toBeDisabled();
      }
    }
  });
});

describe("SchedulingPage — delete action (frontend-page-4 unit-1 / REQ-004)", () => {
  beforeEach(() => {
    mockListScheduledTasks.mockReset();
    mockListDeliveryChannels.mockReset();
    mockCreateScheduledTask.mockReset();
    mockUpdateScheduledTask.mockReset();
    mockCancelScheduledTask.mockReset();
    mockListDeliveryChannels.mockResolvedValue(["web"]);
  });

  it("unit-1: WHEN the user triggers delete and confirms it THEN cancelScheduledTask is called with the task's id and the task is removed from the list", async () => {
    const task = taskFor("task-1", "web:alice");
    mockListScheduledTasks.mockResolvedValue([task]);
    mockCancelScheduledTask.mockResolvedValue(undefined);
    const user = userEvent.setup();

    render(<SchedulingPage />);

    await screen.findByText(task.prompt);
    await user.click(screen.getByRole("button", { name: /excluir/i }));

    const dialog = screen.getByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: /confirmar/i }));

    expect(mockCancelScheduledTask).toHaveBeenCalledWith(task.id);
    expect(screen.queryByText(task.prompt)).not.toBeInTheDocument();
  });

  it("unit-1: WHEN the user triggers delete and does NOT confirm it THEN cancelScheduledTask is not called and the task remains listed", async () => {
    const task = taskFor("task-1", "web:alice");
    mockListScheduledTasks.mockResolvedValue([task]);
    const user = userEvent.setup();

    render(<SchedulingPage />);

    await screen.findByText(task.prompt);
    await user.click(screen.getByRole("button", { name: /excluir/i }));

    const dialog = screen.getByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: /cancelar/i }));

    expect(mockCancelScheduledTask).not.toHaveBeenCalled();
    expect(screen.getByText(task.prompt)).toBeInTheDocument();
  });
});

const marketingProfile = {
  id: "profile-marketing",
  user_id: "alice",
  name: "Assistente de marketing",
  slug: "marketing",
  system_prompt: "Você é o agente de marketing.",
  skills_allowlist: null,
  tools_allowlist: null,
  mcp_allowlist: null,
  tier: 2,
  model_override: null,
  is_active: true,
  archived_at: null,
  created_at: "2026-08-19T00:00:00Z",
  updated_at: "2026-08-19T00:00:00Z",
};

describe("SchedulingPage — profile picker (ui-3 unit-1 / REQ-003)", () => {
  beforeEach(() => {
    mockListScheduledTasks.mockReset();
    mockListDeliveryChannels.mockReset();
    mockCreateScheduledTask.mockReset();
    mockUpdateScheduledTask.mockReset();
    mockListScheduledTasks.mockResolvedValue([]);
    mockListDeliveryChannels.mockResolvedValue(["web"]);
    mockListAgentProfiles.mockResolvedValue([marketingProfile]);
  });

  it("WHEN the user creates a task with a profile selected THEN the API payload includes that profile_id", async () => {
    const created = taskFor("task-profile", "web:alice", {
      prompt: "rode o marketing",
      profile_id: marketingProfile.id,
    });
    mockCreateScheduledTask.mockResolvedValue(created);
    const user = userEvent.setup();

    render(<SchedulingPage />);

    await screen.findByLabelText(/^perfil/i);
    await user.click(screen.getByLabelText(/^perfil/i));
    await user.click(
      await screen.findByRole("option", { name: /assistente de marketing/i })
    );

    await user.type(screen.getByLabelText(/^prompt$/i), created.prompt);
    await user.type(screen.getByLabelText(/expressão/i), "0 9 * * *");
    await user.click(screen.getByRole("button", { name: /criar/i }));

    expect(mockCreateScheduledTask).toHaveBeenCalledWith(
      expect.objectContaining({
        prompt: created.prompt,
        profile_id: marketingProfile.id,
      })
    );
  });

  it("WHEN the user edits a task and picks a profile THEN update sends that profile_id", async () => {
    const task = taskFor("task-edit-profile", "web:alice");
    mockListScheduledTasks.mockResolvedValue([task]);
    mockUpdateScheduledTask.mockResolvedValue({
      ...task,
      profile_id: marketingProfile.id,
    });
    const user = userEvent.setup();

    render(<SchedulingPage />);

    await screen.findByText(task.prompt);
    await user.click(screen.getByRole("button", { name: /editar/i }));

    const dialog = screen.getByRole("dialog");
    await user.click(within(dialog).getByLabelText(/^perfil/i));
    await user.click(
      await screen.findByRole("option", { name: /assistente de marketing/i })
    );
    await user.click(within(dialog).getByRole("button", { name: /salvar/i }));

    expect(mockUpdateScheduledTask).toHaveBeenCalledWith(
      task.id,
      expect.objectContaining({ profile_id: marketingProfile.id })
    );
  });
});

const pesquisaProfile = {
  ...marketingProfile,
  id: "profile-pesquisa",
  name: "Pesquisa",
  slug: "pesquisa",
};

describe("SchedulingPage — picker defaults from chat profileId (ui-3 unit-2 / REQ-003)", () => {
  beforeEach(() => {
    mockListScheduledTasks.mockReset();
    mockListDeliveryChannels.mockReset();
    mockCreateScheduledTask.mockReset();
    mockListScheduledTasks.mockResolvedValue([]);
    mockListDeliveryChannels.mockResolvedValue(["web"]);
    mockListAgentProfiles.mockResolvedValue([marketingProfile, pesquisaProfile]);
    mockGetConfig.mockReturnValue({
      assistantId: "unified",
      profileId: marketingProfile.id,
    });
  });

  it("WHEN create-task opens with config.profileId THEN the select defaults to that profile", async () => {
    mockCreateScheduledTask.mockResolvedValue(
      taskFor("task-default", "web:alice", {
        prompt: "usa o do chat",
        profile_id: marketingProfile.id,
      })
    );
    const user = userEvent.setup();

    render(<SchedulingPage />);

    await user.click(await screen.findByLabelText(/^perfil/i));
    await waitFor(() => {
      expect(
        screen.getByRole("option", { name: /assistente de marketing/i })
      ).toHaveAttribute("data-state", "checked");
    });
    await user.keyboard("{Escape}");

    await user.type(screen.getByLabelText(/^prompt$/i), "usa o do chat");
    await user.type(screen.getByLabelText(/expressão/i), "0 9 * * *");
    await user.click(screen.getByRole("button", { name: /criar/i }));

    expect(mockCreateScheduledTask).toHaveBeenCalledWith(
      expect.objectContaining({ profile_id: marketingProfile.id })
    );
  });

  it("WHEN the defaulted profile is cleared THEN create sends profile_id null", async () => {
    mockCreateScheduledTask.mockResolvedValue(
      taskFor("task-none", "web:alice", { prompt: "sem perfil" })
    );
    const user = userEvent.setup();

    render(<SchedulingPage />);

    await screen.findByLabelText(/^perfil/i);
    await user.click(screen.getByLabelText(/^perfil/i));
    await user.click(
      await screen.findByRole("option", { name: /\(padrão unified\)/i })
    );

    await user.type(screen.getByLabelText(/^prompt$/i), "sem perfil");
    await user.type(screen.getByLabelText(/expressão/i), "0 9 * * *");
    await user.click(screen.getByRole("button", { name: /criar/i }));

    expect(mockCreateScheduledTask).toHaveBeenCalledWith(
      expect.objectContaining({ profile_id: null })
    );
  });

  it("WHEN the defaulted profile is changed THEN create sends the new profile_id", async () => {
    mockCreateScheduledTask.mockResolvedValue(
      taskFor("task-pesquisa", "web:alice", {
        prompt: "troca perfil",
        profile_id: pesquisaProfile.id,
      })
    );
    const user = userEvent.setup();

    render(<SchedulingPage />);

    await screen.findByLabelText(/^perfil/i);
    await user.click(screen.getByLabelText(/^perfil/i));
    await user.click(await screen.findByRole("option", { name: /^pesquisa$/i }));

    await user.type(screen.getByLabelText(/^prompt$/i), "troca perfil");
    await user.type(screen.getByLabelText(/expressão/i), "0 9 * * *");
    await user.click(screen.getByRole("button", { name: /criar/i }));

    expect(mockCreateScheduledTask).toHaveBeenCalledWith(
      expect.objectContaining({ profile_id: pesquisaProfile.id })
    );
  });
});


