"use client";

import { FormEvent, useEffect, useState } from "react";
import { CalendarClock } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  cancelScheduledTask,
  createScheduledTask,
  listScheduledTasks,
  updateScheduledTask,
  type ScheduledTask,
} from "@/lib/scheduling";

function parseSkills(value: string): string[] {
  return value
    .split(",")
    .map((skill) => skill.trim())
    .filter(Boolean);
}

export default function SchedulingPage() {
  const [tasks, setTasks] = useState<ScheduledTask[]>([]);
  const [prompt, setPrompt] = useState("");
  const [scheduleKind, setScheduleKind] = useState("cron");
  const [scheduleExpr, setScheduleExpr] = useState("");
  const [toolScope, setToolScope] = useState("restricted");
  const [skills, setSkills] = useState("");

  const [deletingTask, setDeletingTask] = useState<ScheduledTask | null>(null);

  const [editingTask, setEditingTask] = useState<ScheduledTask | null>(null);
  const [editPrompt, setEditPrompt] = useState("");
  const [editScheduleKind, setEditScheduleKind] = useState("cron");
  const [editScheduleExpr, setEditScheduleExpr] = useState("");
  const [editToolScope, setEditToolScope] = useState("restricted");
  const [editSkills, setEditSkills] = useState("");

  useEffect(() => {
    listScheduledTasks().then(setTasks);
  }, []);

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    const created = await createScheduledTask({
      prompt,
      schedule_kind: scheduleKind,
      schedule_expr: scheduleExpr,
      tool_scope: toolScope,
      skills: parseSkills(skills),
    });
    setTasks((current) => [...current, created]);
    setPrompt("");
    setScheduleExpr("");
    setSkills("");
  };

  const onConfirmDelete = async () => {
    if (!deletingTask) return;
    await cancelScheduledTask(deletingTask.id);
    setTasks((current) => current.filter((task) => task.id !== deletingTask.id));
    setDeletingTask(null);
  };

  const openEditDialog = (task: ScheduledTask) => {
    setEditingTask(task);
    setEditPrompt(task.prompt);
    setEditScheduleKind(task.schedule_kind);
    setEditScheduleExpr(task.schedule_expr);
    setEditToolScope(task.tool_scope);
    setEditSkills(task.skills.join(", "));
  };

  const onEditSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (!editingTask) return;
    const updated = await updateScheduledTask(editingTask.id, {
      prompt: editPrompt,
      schedule_kind: editScheduleKind,
      schedule_expr: editScheduleExpr,
      tool_scope: editToolScope,
      skills: parseSkills(editSkills),
    });
    setTasks((current) =>
      current.map((task) => (task.id === updated.id ? updated : task))
    );
    setEditingTask(null);
  };

  return (
    <div className="min-h-screen bg-background">
      <header className="sticky top-0 z-40 border-b border-border bg-background/80 backdrop-blur-sm">
        <div className="mx-auto flex max-w-[960px] items-center gap-3 px-6 py-4">
          <CalendarClock size={24} className="text-primary" aria-hidden="true" />
          <h1 className="text-xl font-semibold">Agendamentos</h1>
        </div>
      </header>

      <main className="mx-auto flex max-w-[960px] flex-col gap-8 px-6 py-8">
        <form
          onSubmit={onSubmit}
          className="flex flex-col gap-4"
          aria-label="Criar agendamento"
        >
          <div className="flex flex-col gap-2">
            <Label htmlFor="scheduling-prompt">Prompt</Label>
            <Textarea
              id="scheduling-prompt"
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              required
            />
          </div>

          <div className="flex flex-col gap-4 sm:flex-row">
            <div className="flex flex-1 flex-col gap-2">
              <Label htmlFor="scheduling-kind">Tipo de agendamento</Label>
              <Select value={scheduleKind} onValueChange={setScheduleKind}>
                <SelectTrigger id="scheduling-kind">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="cron">Recorrente (cron)</SelectItem>
                  <SelectItem value="once">Uma vez</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="flex flex-1 flex-col gap-2">
              <Label htmlFor="scheduling-expr">Expressão de agendamento</Label>
              <Input
                id="scheduling-expr"
                value={scheduleExpr}
                onChange={(e) => setScheduleExpr(e.target.value)}
                placeholder={scheduleKind === "cron" ? "0 9 * * *" : "2026-12-31T23:59:00"}
                required
              />
            </div>
          </div>

          <div className="flex flex-col gap-4 sm:flex-row">
            <div className="flex flex-1 flex-col gap-2">
              <Label htmlFor="scheduling-tool-scope">Escopo de ferramentas</Label>
              <Select value={toolScope} onValueChange={setToolScope}>
                <SelectTrigger id="scheduling-tool-scope">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="restricted">Restrito</SelectItem>
                  <SelectItem value="full">Completo</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="flex flex-1 flex-col gap-2">
              <Label htmlFor="scheduling-skills">Skills (separadas por vírgula)</Label>
              <Input
                id="scheduling-skills"
                value={skills}
                onChange={(e) => setSkills(e.target.value)}
              />
            </div>
          </div>

          <Button type="submit">Criar agendamento</Button>
        </form>

        <ul className="flex flex-col gap-2">
          {tasks.map((task) => (
            <li
              key={task.id}
              className="flex items-center justify-between gap-4 rounded-md border border-border bg-card p-4 text-sm"
            >
              <span>{task.prompt}</span>
              <div className="flex items-center gap-2">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={task.status !== "scheduled"}
                  onClick={() => openEditDialog(task)}
                >
                  Editar
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => setDeletingTask(task)}
                >
                  Excluir
                </Button>
              </div>
            </li>
          ))}
        </ul>
      </main>

      <Dialog
        open={editingTask !== null}
        onOpenChange={(open) => {
          if (!open) setEditingTask(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Editar agendamento</DialogTitle>
          </DialogHeader>

          <form onSubmit={onEditSubmit} className="flex flex-col gap-4">
            <div className="flex flex-col gap-2">
              <Label htmlFor="edit-scheduling-prompt">Prompt</Label>
              <Textarea
                id="edit-scheduling-prompt"
                value={editPrompt}
                onChange={(e) => setEditPrompt(e.target.value)}
                required
              />
            </div>

            <div className="flex flex-col gap-4 sm:flex-row">
              <div className="flex flex-1 flex-col gap-2">
                <Label htmlFor="edit-scheduling-kind">Tipo de agendamento</Label>
                <Select value={editScheduleKind} onValueChange={setEditScheduleKind}>
                  <SelectTrigger id="edit-scheduling-kind">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="cron">Recorrente (cron)</SelectItem>
                    <SelectItem value="once">Uma vez</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="flex flex-1 flex-col gap-2">
                <Label htmlFor="edit-scheduling-expr">Expressão de agendamento</Label>
                <Input
                  id="edit-scheduling-expr"
                  value={editScheduleExpr}
                  onChange={(e) => setEditScheduleExpr(e.target.value)}
                  required
                />
              </div>
            </div>

            <div className="flex flex-col gap-4 sm:flex-row">
              <div className="flex flex-1 flex-col gap-2">
                <Label htmlFor="edit-scheduling-tool-scope">Escopo de ferramentas</Label>
                <Select value={editToolScope} onValueChange={setEditToolScope}>
                  <SelectTrigger id="edit-scheduling-tool-scope">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="restricted">Restrito</SelectItem>
                    <SelectItem value="full">Completo</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="flex flex-1 flex-col gap-2">
                <Label htmlFor="edit-scheduling-skills">Skills (separadas por vírgula)</Label>
                <Input
                  id="edit-scheduling-skills"
                  value={editSkills}
                  onChange={(e) => setEditSkills(e.target.value)}
                />
              </div>
            </div>

            <DialogFooter>
              <Button type="submit">Salvar</Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog
        open={deletingTask !== null}
        onOpenChange={(open) => {
          if (!open) setDeletingTask(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Excluir agendamento</DialogTitle>
          </DialogHeader>

          <p className="text-sm text-muted-foreground">
            Tem certeza que deseja excluir este agendamento? Essa ação não pode ser desfeita.
          </p>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setDeletingTask(null)}>
              Cancelar
            </Button>
            <Button type="button" variant="destructive" onClick={onConfirmDelete}>
              Confirmar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
