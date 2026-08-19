"use client";

import { FormEvent, useState, useEffect } from "react";
import { Bot, Plus } from "lucide-react";

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
  archiveAgentProfile,
  createAgentProfile,
  listAgentProfiles,
  updateAgentProfile,
  type AgentProfile,
} from "@/lib/agent-profiles";

function parseAllowlist(value: string): string[] | null {
  const items = value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
  return items.length === 0 ? null : items;
}

function allowlistToText(value: string[] | null | undefined): string {
  return (value ?? []).join(", ");
}

export default function AgentProfilesPage() {
  const [profiles, setProfiles] = useState<AgentProfile[]>([]);
  const [archiving, setArchiving] = useState<AgentProfile | null>(null);
  const [editorOpen, setEditorOpen] = useState(false);
  const [editing, setEditing] = useState<AgentProfile | null>(null);

  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [systemPrompt, setSystemPrompt] = useState("");
  const [skills, setSkills] = useState("");
  const [tools, setTools] = useState("");
  const [mcp, setMcp] = useState("");
  const [tier, setTier] = useState("1");
  const [modelOverride, setModelOverride] = useState("");

  useEffect(() => {
    listAgentProfiles().then(setProfiles);
  }, []);

  const resetForm = (profile?: AgentProfile | null) => {
    setName(profile?.name ?? "");
    setSlug(profile?.slug ?? "");
    setSystemPrompt(profile?.system_prompt ?? "");
    setSkills(allowlistToText(profile?.skills_allowlist));
    setTools(allowlistToText(profile?.tools_allowlist));
    setMcp(allowlistToText(profile?.mcp_allowlist));
    setTier(String(profile?.tier ?? 1));
    setModelOverride(profile?.model_override ?? "");
  };

  const openCreate = () => {
    setEditing(null);
    resetForm(null);
    setEditorOpen(true);
  };

  const openEdit = (profile: AgentProfile) => {
    setEditing(profile);
    resetForm(profile);
    setEditorOpen(true);
  };

  const onConfirmArchive = async () => {
    if (!archiving) return;
    await archiveAgentProfile(archiving.id);
    setProfiles((current) =>
      current.filter((profile) => profile.id !== archiving.id)
    );
    setArchiving(null);
  };

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    const payload = {
      name,
      system_prompt: systemPrompt,
      skills_allowlist: parseAllowlist(skills),
      tools_allowlist: parseAllowlist(tools),
      mcp_allowlist: parseAllowlist(mcp),
      tier: Number(tier),
      model_override: modelOverride.trim() === "" ? null : modelOverride.trim(),
    };

    if (editing) {
      const updated = await updateAgentProfile(editing.id, payload);
      setProfiles((current) =>
        current.map((profile) => (profile.id === updated.id ? updated : profile))
      );
    } else {
      const created = await createAgentProfile({ ...payload, slug });
      setProfiles((current) => [...current, created]);
    }
    setEditorOpen(false);
    setEditing(null);
  };

  return (
    <div className="min-h-screen bg-background">
      <header className="sticky top-0 z-40 border-b border-border bg-background/80 backdrop-blur-sm">
        <div className="mx-auto flex max-w-[960px] items-center gap-3 px-6 py-4">
          <Bot size={24} className="text-primary" aria-hidden="true" />
          <h1 className="text-xl font-semibold">Perfis de agente</h1>
          <Button size="sm" className="ml-auto" onClick={openCreate}>
            <Plus className="mr-2 h-4 w-4" />
            Novo perfil
          </Button>
        </div>
      </header>

      <main className="mx-auto flex max-w-[960px] flex-col gap-8 px-6 py-8">
        {profiles.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Você ainda não tem perfis de agente.
          </p>
        ) : (
          <ul className="flex flex-col gap-3">
            {profiles.map((profile) => (
              <li
                key={profile.id}
                className="flex items-center justify-between rounded-md border border-border p-4"
              >
                <div className="flex min-w-0 flex-col">
                  <span className="font-medium">{profile.name}</span>
                  <span className="text-xs text-muted-foreground">
                    {profile.slug}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => openEdit(profile)}
                  >
                    Editar
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => setArchiving(profile)}
                  >
                    Arquivar
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </main>

      <Dialog
        open={editorOpen}
        onOpenChange={(open) => {
          setEditorOpen(open);
          if (!open) setEditing(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {editing ? "Editar perfil" : "Novo perfil"}
            </DialogTitle>
          </DialogHeader>

          <form onSubmit={onSubmit} className="flex flex-col gap-4">
            <div className="flex flex-col gap-2">
              <Label htmlFor="profile-name">Nome</Label>
              <Input
                id="profile-name"
                value={name}
                onChange={(event) => setName(event.target.value)}
                required
              />
            </div>

            {!editing ? (
              <div className="flex flex-col gap-2">
                <Label htmlFor="profile-slug">Slug</Label>
                <Input
                  id="profile-slug"
                  value={slug}
                  onChange={(event) => setSlug(event.target.value)}
                  required
                />
              </div>
            ) : null}

            <div className="flex flex-col gap-2">
              <Label htmlFor="profile-system-prompt">Prompt do sistema</Label>
              <Textarea
                id="profile-system-prompt"
                value={systemPrompt}
                onChange={(event) => setSystemPrompt(event.target.value)}
                required
              />
            </div>

            <div className="flex flex-col gap-2">
              <Label htmlFor="profile-skills">Skills</Label>
              <Input
                id="profile-skills"
                value={skills}
                onChange={(event) => setSkills(event.target.value)}
                placeholder="brand-guidelines, arxiv-search"
              />
            </div>

            <div className="flex flex-col gap-2">
              <Label htmlFor="profile-tools">Ferramentas</Label>
              <Input
                id="profile-tools"
                value={tools}
                onChange={(event) => setTools(event.target.value)}
                placeholder="web_search, save_memory"
              />
            </div>

            <div className="flex flex-col gap-2">
              <Label htmlFor="profile-mcp">MCP</Label>
              <Input
                id="profile-mcp"
                value={mcp}
                onChange={(event) => setMcp(event.target.value)}
                placeholder="gmail"
              />
            </div>

            <div className="flex flex-col gap-4 sm:flex-row">
              <div className="flex flex-1 flex-col gap-2">
                <Label htmlFor="profile-tier">Nível (tier)</Label>
                <Select value={tier} onValueChange={setTier}>
                  <SelectTrigger id="profile-tier">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="1">1</SelectItem>
                    <SelectItem value="2">2</SelectItem>
                    <SelectItem value="3">3</SelectItem>
                    <SelectItem value="4">4</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="flex flex-1 flex-col gap-2">
                <Label htmlFor="profile-model">Modelo (opcional)</Label>
                <Input
                  id="profile-model"
                  value={modelOverride}
                  onChange={(event) => setModelOverride(event.target.value)}
                />
              </div>
            </div>

            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => setEditorOpen(false)}
              >
                Cancelar
              </Button>
              <Button type="submit">Salvar</Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog
        open={archiving !== null}
        onOpenChange={(open) => {
          if (!open) setArchiving(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Arquivar perfil</DialogTitle>
          </DialogHeader>

          <p className="text-sm text-muted-foreground">
            Tem certeza que deseja arquivar este perfil? Ele deixa de aparecer
            na lista e nas escolhas de execução.
          </p>

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => setArchiving(null)}
            >
              Cancelar
            </Button>
            <Button type="button" variant="destructive" onClick={onConfirmArchive}>
              Confirmar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
