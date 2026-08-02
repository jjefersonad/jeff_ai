import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import SchedulingPage from "./page";

const mockListScheduledTasks = vi.fn();
const mockCreateScheduledTask = vi.fn();
const mockUpdateScheduledTask = vi.fn();
const mockCancelScheduledTask = vi.fn();

vi.mock("@/lib/scheduling", () => ({
  listScheduledTasks: (...args: unknown[]) => mockListScheduledTasks(...args),
  createScheduledTask: (...args: unknown[]) => mockCreateScheduledTask(...args),
  updateScheduledTask: (...args: unknown[]) => mockUpdateScheduledTask(...args),
  cancelScheduledTask: (...args: unknown[]) => mockCancelScheduledTask(...args),
}));

const taskFor = (id: string, owner: string) => ({
  id,
  prompt: `Prompt ${id}`,
  thread_id: `thread-${id}`,
  schedule_kind: "cron",
  schedule_expr: "0 9 * * *",
  tool_scope: "restricted",
  skills: [],
  timeout_seconds: 300,
  status: "SCHEDULED",
  owner_user_key: owner,
  started_at: null,
  finished_at: null,
  error: null,
  created_at: "2026-07-28T00:00:00Z",
});

describe("SchedulingPage (frontend-page-1 unit-1/unit-2 / REQ-001)", () => {
  beforeEach(() => {
    mockListScheduledTasks.mockReset();
    mockCreateScheduledTask.mockReset();
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
    mockCreateScheduledTask.mockReset();
    mockListScheduledTasks.mockResolvedValue([]);
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
      })
    );
    expect(await screen.findByText(created.prompt)).toBeInTheDocument();
  });
});

describe("SchedulingPage — edit action (frontend-page-3 / REQ-003)", () => {
  beforeEach(() => {
    mockListScheduledTasks.mockReset();
    mockCreateScheduledTask.mockReset();
    mockUpdateScheduledTask.mockReset();
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
      { ...taskFor("task-running", "web:alice"), status: "RUNNING" },
      { ...taskFor("task-succeeded", "web:alice"), status: "SUCCEEDED" },
      { ...taskFor("task-failed", "web:alice"), status: "FAILED" },
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
    mockCreateScheduledTask.mockReset();
    mockUpdateScheduledTask.mockReset();
    mockCancelScheduledTask.mockReset();
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
