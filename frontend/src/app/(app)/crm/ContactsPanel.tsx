"use client";

/**
 * Aba Contatos — tabela/cards, search, Dialog create/edit, toast, paginação,
 * city/state/custom fields e timestamps readonly.
 *
 * Três diálogos independentes: Detalhes (readonly + notas), Form (criar/editar)
 * e Delete (confirmação). O antigo `returnToDetail` foi removido — Cancelar no
 * Form fecha apenas o Form; o usuário só vê Detalhes ao clicar no nome da
 * linha. Ver bug-report em `.project/task-todo.md`.
 */

import { FormEvent, useCallback, useEffect, useState } from "react";
import { Pencil, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ApiError } from "@/lib/api";
import {
  archiveContact,
  buildContactWritePayload,
  createContact,
  createFieldDefinition,
  formatCrmTimestamp,
  getContact,
  listContacts,
  listFieldDefinitions,
  slugifyFieldKey,
  updateContact,
  validateContactForm,
  type CrmCompany,
  type CrmContact,
  type CrmFieldDefinition,
  type CrmNote,
} from "@/lib/crm";

const PAGE_SIZE = 20;

function errMessage(err: unknown): string {
  return err instanceof ApiError ? err.message : "Falha inesperada";
}

type ContactFormState = {
  name: string;
  email: string;
  phone: string;
  company_id: string;
  city: string;
  state: string;
  custom_values: Record<string, string>;
};

const emptyForm = (): ContactFormState => ({
  name: "",
  email: "",
  phone: "",
  company_id: "none",
  city: "",
  state: "",
  custom_values: {},
});

function formFromContact(contact: CrmContact): ContactFormState {
  const custom: Record<string, string> = {};
  for (const [key, value] of Object.entries(contact.custom_values ?? {})) {
    custom[key] = value == null ? "" : String(value);
  }
  return {
    name: contact.name,
    email: contact.email ?? "",
    phone: contact.phone ?? "",
    company_id: contact.company_id ?? "none",
    city: contact.city ?? "",
    state: contact.state ?? "",
    custom_values: custom,
  };
}

type Props = {
  companies: CrmCompany[];
  selectedContactId: string | null;
  onSelectContact: (id: string | null) => void;
  notes: CrmNote[];
  noteBody: string;
  setNoteBody: (value: string) => void;
  onAddNote: (event: FormEvent) => void;
  onContactsChanged: () => void;
};

export function ContactsPanel({
  companies,
  selectedContactId,
  onSelectContact,
  notes,
  noteBody,
  setNoteBody,
  onAddNote,
  onContactsChanged,
}: Props) {
  const [contacts, setContacts] = useState<CrmContact[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [query, setQuery] = useState("");
  const [searchDraft, setSearchDraft] = useState("");
  const [definitions, setDefinitions] = useState<CrmFieldDefinition[]>([]);
  const [error, setError] = useState<string | null>(null);

  // Três diálogos independentes:
  //   * `detailOpen` — Detalhes (readonly + notas); aberto ao clicar no nome.
  //   * `formOpen` — Adicionar / Editar (formulário).
  //   * `deleteTarget != null` — confirmação de exclusão.
  const [detailOpen, setDetailOpen] = useState(false);
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<CrmContact | null>(null); // null = criar
  const [form, setForm] = useState<ContactFormState>(emptyForm);
  const [formError, setFormError] = useState<string | null>(null);

  const [deleteTarget, setDeleteTarget] = useState<CrmContact | null>(null);

  const [newFieldKey, setNewFieldKey] = useState("");
  const [newFieldLabel, setNewFieldLabel] = useState("");
  const [newFieldType, setNewFieldType] = useState("text");

  const loadPage = useCallback(async () => {
    const result = await listContacts({
      query: query || undefined,
      page,
      page_size: PAGE_SIZE,
    });
    setContacts(result.items ?? []);
    setTotal(result.total ?? 0);
  }, [page, query]);

  const loadDefinitions = useCallback(async () => {
    const defs = await listFieldDefinitions({ entity: "contact" });
    setDefinitions(defs);
  }, []);

  useEffect(() => {
    loadPage().catch((err) => setError(errMessage(err)));
  }, [loadPage]);

  useEffect(() => {
    loadDefinitions().catch((err) => setError(errMessage(err)));
  }, [loadDefinitions]);

  // Cancela/fecha o formulário: limpa form, editing e erro. Não toca em
  // `detailOpen` — Cancelar apenas fecha o formulário e devolve o usuário à
  // tabela. Para ver Detalhes novamente ele precisa clicar no nome da linha.
  const resetForm = () => {
    setFormOpen(false);
    setEditing(null);
    setForm(emptyForm());
    setFormError(null);
  };

  const openDetail = (contact: CrmContact) => {
    onSelectContact(contact.id);
    setDetailOpen(true);
  };

  const openCreate = () => {
    setEditing(null);
    setForm(emptyForm());
    setFormError(null);
    setFormOpen(true);
    loadDefinitions().catch((err) => setFormError(errMessage(err)));
  };

  const openEdit = (contact: CrmContact) => {
    setEditing(contact);
    setForm(formFromContact(contact));
    setFormError(null);
    setFormOpen(true);
    onSelectContact(contact.id);
    void (async () => {
      try {
        const [fresh, defs] = await Promise.all([
          getContact(contact.id),
          listFieldDefinitions({ entity: "contact" }),
        ]);
        setDefinitions(defs);
        setEditing(fresh);
        setForm(formFromContact(fresh));
      } catch (err) {
        setFormError(errMessage(err));
      }
    })();
  };

  const customValuesPayload = (
    defs: CrmFieldDefinition[] = definitions
  ): Record<string, unknown> => {
    const out: Record<string, unknown> = {};
    for (const def of defs) {
      const raw = form.custom_values[def.key];
      if (raw === undefined || raw === "") continue;
      if (def.field_type === "number") {
        const n = Number(raw);
        if (!Number.isNaN(n)) out[def.key] = n;
      } else if (def.field_type === "boolean") {
        out[def.key] = raw === "true" || raw === "1";
      } else {
        out[def.key] = raw;
      }
    }
    return out;
  };

  const ensurePendingDefinition = async (): Promise<CrmFieldDefinition[]> => {
    const label = newFieldLabel.trim();
    const key = slugifyFieldKey(newFieldKey.trim() || label);
    if (!label && !newFieldKey.trim()) return definitions;
    if (!label || !key) {
      throw new Error(
        "Para criar o campo personalizado, informe rótulo (e chave válida)."
      );
    }
    const created = await createFieldDefinition({
      entity: "contact",
      key,
      label,
      field_type: newFieldType,
    });
    setNewFieldKey("");
    setNewFieldLabel("");
    const next = [...definitions.filter((d) => d.key !== created.key), created];
    setDefinitions(next);
    setForm((f) => ({
      ...f,
      custom_values: {
        ...f.custom_values,
        [created.key]: f.custom_values[created.key] ?? "",
      },
    }));
    return next;
  };

  const onSubmitForm = async (event: FormEvent) => {
    event.preventDefault();
    const validation = validateContactForm({
      name: form.name,
      email: form.email,
      phone: form.phone,
    });
    if (!validation.valid) {
      setFormError(validation.error ?? "Dados inválidos");
      return;
    }
    setFormError(null);
    try {
      let defs = definitions;
      if (newFieldKey.trim() || newFieldLabel.trim()) {
        defs = await ensurePendingDefinition();
      }
      const payload = buildContactWritePayload({
        name: form.name,
        email: form.email,
        phone: form.phone,
        company_id: form.company_id === "none" ? null : form.company_id,
        city: form.city,
        state: form.state,
        custom_values: customValuesPayload(defs),
        created_at: editing?.created_at,
        updated_at: editing?.updated_at,
      });
      if (editing) {
        const updated = await updateContact(editing.id, {
          ...payload,
          clear_company: form.company_id === "none",
        });
        toast.success("Contato atualizado");
        onSelectContact(updated.id);
      } else {
        const created = await createContact(payload);
        toast.success("Contato cadastrado");
        onSelectContact(created.id);
      }
      resetForm();
      await loadPage();
      onContactsChanged();
    } catch (err) {
      setFormError(errMessage(err));
    }
  };

  const onConfirmDelete = async () => {
    if (!deleteTarget) return;
    try {
      await archiveContact(deleteTarget.id);
      toast.success("Contato excluído (arquivado)");
      if (selectedContactId === deleteTarget.id) onSelectContact(null);
      setDeleteTarget(null);
      await loadPage();
      onContactsChanged();
    } catch (err) {
      setError(errMessage(err));
    }
  };

  const onCreateDefinition = async () => {
    try {
      await ensurePendingDefinition();
      toast.success("Campo personalizado criado");
    } catch (err) {
      setFormError(errMessage(err));
    }
  };

  const selected =
    (contacts ?? []).find((c) => c.id === selectedContactId) ?? null;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className="flex flex-col gap-4">
      {error && (
        <p className="text-sm text-destructive" role="alert">
          {error}
        </p>
      )}

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <Input
          placeholder="Buscar por nome, e-mail ou telefone"
          value={searchDraft}
          onChange={(e) => setSearchDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              setPage(1);
              setQuery(searchDraft.trim());
            }
          }}
          aria-label="Buscar contatos"
          className="sm:max-w-sm"
        />
        <Button
          type="button"
          variant="secondary"
          onClick={() => {
            setPage(1);
            setQuery(searchDraft.trim());
          }}
        >
          Buscar
        </Button>
        <Button type="button" className="sm:ml-auto" onClick={openCreate}>
          Adicionar
        </Button>
      </div>

      {/* Desktop table */}
      <div className="hidden md:block overflow-x-auto rounded-md border border-border">
        <table className="w-full text-sm">
          <thead className="border-b border-border bg-muted/40 text-left">
            <tr>
              <th className="px-3 py-2 font-medium">Nome</th>
              <th className="px-3 py-2 font-medium">E-mail</th>
              <th className="px-3 py-2 font-medium">Telefone</th>
              <th className="px-3 py-2 font-medium">Atualizado</th>
              <th className="px-3 py-2 font-medium">Ações</th>
            </tr>
          </thead>
          <tbody>
            {contacts.map((contact) => (
              <tr
                key={contact.id}
                className={`border-b border-border last:border-0 ${
                  selectedContactId === contact.id ? "bg-accent/50" : ""
                }`}
              >
                <td className="px-3 py-2">
                  <button
                    type="button"
                    className="font-medium hover:underline"
                    onClick={() => openDetail(contact)}
                  >
                    {contact.name}
                  </button>
                </td>
                <td className="px-3 py-2 text-muted-foreground">
                  {contact.email ?? "—"}
                </td>
                <td className="px-3 py-2 text-muted-foreground">
                  {contact.phone ?? "—"}
                </td>
                <td className="px-3 py-2 text-muted-foreground">
                  {formatCrmTimestamp(contact.updated_at)}
                </td>
                <td className="px-3 py-2">
                  <div className="flex gap-1">
                    <Button
                      type="button"
                      size="icon"
                      variant="ghost"
                      aria-label={`Editar ${contact.name}`}
                      onClick={() => openEdit(contact)}
                    >
                      <Pencil className="size-4" />
                    </Button>
                    <Button
                      type="button"
                      size="icon"
                      variant="ghost"
                      aria-label={`Excluir ${contact.name}`}
                      onClick={() => setDeleteTarget(contact)}
                    >
                      <Trash2 className="size-4" />
                    </Button>
                  </div>
                </td>
              </tr>
            ))}
            {contacts.length === 0 && (
              <tr>
                <td
                  colSpan={5}
                  className="px-3 py-6 text-center text-muted-foreground"
                >
                  Nenhum contato encontrado.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Mobile cards */}
      <ul className="flex flex-col gap-3 md:hidden">
        {contacts.map((contact) => (
          <li
            key={contact.id}
            className={`rounded-md border border-border p-3 ${
              selectedContactId === contact.id ? "bg-accent/40" : ""
            }`}
          >
            <button
              type="button"
              className="w-full text-left"
              onClick={() => openDetail(contact)}
            >
              <span className="font-medium">{contact.name}</span>
              <span className="mt-1 block text-xs text-muted-foreground">
                {contact.email || contact.phone || "—"}
              </span>
              <span className="mt-1 block text-xs text-muted-foreground">
                Atualizado {formatCrmTimestamp(contact.updated_at)}
              </span>
            </button>
            <div className="mt-2 flex gap-2">
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={() => openEdit(contact)}
              >
                Editar
              </Button>
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={() => setDeleteTarget(contact)}
              >
                Excluir
              </Button>
            </div>
          </li>
        ))}
      </ul>

      <div className="flex items-center justify-between gap-2 text-sm">
        <span className="text-muted-foreground">
          {total} contato{total === 1 ? "" : "s"}
        </span>
        <div className="flex items-center gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={page <= 1}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
          >
            Anterior
          </Button>
          <span>
            {page} / {totalPages}
          </span>
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={page >= totalPages}
            onClick={() => setPage((p) => p + 1)}
          >
            Próxima
          </Button>
        </div>
      </div>

      {/* Diálogo 1 — Detalhes (readonly + notas). Aberto ao clicar no nome. */}
      <Dialog
        open={
          detailOpen && selected != null && !formOpen && deleteTarget == null
        }
        onOpenChange={(open) => {
          if (open) return;
          setDetailOpen(false);
          onSelectContact(null);
        }}
      >
        <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>{selected?.name ?? "Detalhe"}</DialogTitle>
            <DialogDescription>
              Detalhes do contato, timestamps e notas.
            </DialogDescription>
          </DialogHeader>
          {selected && (
            <div className="flex flex-col gap-4">
              <dl className="grid gap-2 text-sm sm:grid-cols-2">
                <div>
                  <dt className="text-muted-foreground">E-mail</dt>
                  <dd>{selected.email ?? "—"}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Telefone</dt>
                  <dd>{selected.phone ?? "—"}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Cidade / UF</dt>
                  <dd>
                    {[selected.city, selected.state]
                      .filter(Boolean)
                      .join(" / ") || "—"}
                  </dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Criado</dt>
                  <dd>{formatCrmTimestamp(selected.created_at)}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Atualizado</dt>
                  <dd>{formatCrmTimestamp(selected.updated_at)}</dd>
                </div>
                {Object.entries(selected.custom_values ?? {}).map(
                  ([key, value]) => (
                    <div key={key}>
                      <dt className="text-muted-foreground">{key}</dt>
                      <dd>{value == null ? "—" : String(value)}</dd>
                    </div>
                  )
                )}
              </dl>
              <DialogFooter className="gap-2 sm:justify-start">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => {
                    setDetailOpen(false);
                    openEdit(selected);
                  }}
                >
                  Editar
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setDeleteTarget(selected)}
                >
                  Excluir
                </Button>
              </DialogFooter>
              <NotesBlock
                notes={notes}
                noteBody={noteBody}
                setNoteBody={setNoteBody}
                onAddNote={onAddNote}
              />
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Diálogo 2 — Form (Adicionar / Editar). Cancelar fecha apenas este. */}
      <Dialog
        open={formOpen && deleteTarget == null}
        onOpenChange={(open) => {
          if (open) return;
          resetForm();
        }}
      >
        <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>
              {editing ? "Editar contato" : "Novo contato"}
            </DialogTitle>
            <DialogDescription>
              Campos com * são obrigatórios (nome + e-mail ou telefone).
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={onSubmitForm} className="flex flex-col gap-3">
            <div className="flex flex-col gap-1">
              <Label htmlFor="modal-contact-name">Nome *</Label>
              <Input
                id="modal-contact-name"
                value={form.name}
                onChange={(e) =>
                  setForm((f) => ({ ...f, name: e.target.value }))
                }
              />
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="flex flex-col gap-1">
                <Label htmlFor="modal-contact-email">E-mail</Label>
                <Input
                  id="modal-contact-email"
                  type="email"
                  value={form.email}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, email: e.target.value }))
                  }
                />
              </div>
              <div className="flex flex-col gap-1">
                <Label htmlFor="modal-contact-phone">Telefone</Label>
                <Input
                  id="modal-contact-phone"
                  value={form.phone}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, phone: e.target.value }))
                  }
                />
              </div>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="flex flex-col gap-1">
                <Label htmlFor="modal-contact-city">Cidade</Label>
                <Input
                  id="modal-contact-city"
                  value={form.city}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, city: e.target.value }))
                  }
                />
              </div>
              <div className="flex flex-col gap-1">
                <Label htmlFor="modal-contact-state">UF</Label>
                <Input
                  id="modal-contact-state"
                  value={form.state}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, state: e.target.value }))
                  }
                />
              </div>
            </div>
            <div className="flex flex-col gap-1">
              <Label>Empresa</Label>
              <Select
                value={form.company_id}
                onValueChange={(value) =>
                  setForm((f) => ({ ...f, company_id: value }))
                }
              >
                <SelectTrigger className="h-9 bg-transparent">
                  <SelectValue placeholder="Sem empresa" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">Sem empresa</SelectItem>
                  {companies.map((company) => (
                    <SelectItem key={company.id} value={company.id}>
                      {company.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {definitions.length > 0 && (
              <div className="flex flex-col gap-2 rounded-md border border-border p-3">
                <h3 className="text-sm font-medium">
                  Campos personalizados
                </h3>
                {definitions.map((def) => (
                  <div key={def.id} className="flex flex-col gap-1">
                    <Label htmlFor={`cf-${def.key}`}>{def.label}</Label>
                    {def.field_type === "boolean" ? (
                      <Select
                        value={form.custom_values[def.key] ?? ""}
                        onValueChange={(value) =>
                          setForm((f) => ({
                            ...f,
                            custom_values: {
                              ...f.custom_values,
                              [def.key]: value,
                            },
                          }))
                        }
                      >
                        <SelectTrigger id={`cf-${def.key}`}>
                          <SelectValue placeholder="—" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="true">Sim</SelectItem>
                          <SelectItem value="false">Não</SelectItem>
                        </SelectContent>
                      </Select>
                    ) : (
                      <Input
                        id={`cf-${def.key}`}
                        type={def.field_type === "number" ? "number" : "text"}
                        value={form.custom_values[def.key] ?? ""}
                        onChange={(e) =>
                          setForm((f) => ({
                            ...f,
                            custom_values: {
                              ...f.custom_values,
                              [def.key]: e.target.value,
                            },
                          }))
                        }
                      />
                    )}
                  </div>
                ))}
              </div>
            )}

            <div className="flex flex-col gap-2 rounded-md border border-dashed border-border p-3">
              <h3 className="text-sm font-medium">
                Campo personalizado
              </h3>
              <div className="grid gap-2 sm:grid-cols-3">
                <Input
                  placeholder="chave (opcional)"
                  value={newFieldKey}
                  onChange={(e) => setNewFieldKey(e.target.value)}
                />
                <Input
                  placeholder="rótulo *"
                  value={newFieldLabel}
                  onChange={(e) => setNewFieldLabel(e.target.value)}
                />
                <Select value={newFieldType} onValueChange={setNewFieldType}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="text">text</SelectItem>
                    <SelectItem value="number">number</SelectItem>
                    <SelectItem value="boolean">boolean</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <Button
                type="button"
                variant="secondary"
                onClick={onCreateDefinition}
              >
                Cadastrar definição
              </Button>
            </div>

            {editing && (
              <dl className="grid gap-1 text-xs text-muted-foreground sm:grid-cols-2">
                <div>
                  <dt>Criado</dt>
                  <dd>{formatCrmTimestamp(editing.created_at)}</dd>
                </div>
                <div>
                  <dt>Atualizado</dt>
                  <dd>{formatCrmTimestamp(editing.updated_at)}</dd>
                </div>
              </dl>
            )}

            {formError && (
              <p className="text-sm text-destructive" role="alert">
                {formError}
              </p>
            )}
            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={resetForm}
              >
                Cancelar
              </Button>
              <Button type="submit">
                {editing ? "Salvar" : "Criar"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Diálogo 3 — confirmação de exclusão. */}
      <Dialog
        open={deleteTarget != null}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Excluir contato?</DialogTitle>
            <DialogDescription>
              Isso arquiva o contato e também notas e deals vinculados. A ação
              é recuperável (soft-archive), mas remove o contato da lista
              padrão.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => setDeleteTarget(null)}
            >
              Cancelar
            </Button>
            <Button type="button" variant="destructive" onClick={onConfirmDelete}>
              Excluir
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function NotesBlock({
  notes,
  noteBody,
  setNoteBody,
  onAddNote,
}: {
  notes: CrmNote[];
  noteBody: string;
  setNoteBody: (value: string) => void;
  onAddNote: (event: FormEvent) => void;
}) {
  return (
    <div className="flex flex-col gap-3 border-t border-border pt-4">
      <h3 className="text-sm font-medium">Notas</h3>
      <form onSubmit={onAddNote} className="flex flex-col gap-2">
        <textarea
          className="min-h-[72px] rounded-md border border-input bg-transparent px-3 py-2 text-sm"
          value={noteBody}
          onChange={(e) => setNoteBody(e.target.value)}
          placeholder="Nova nota…"
        />
        <Button type="submit" size="sm" className="self-start">
          Adicionar nota
        </Button>
      </form>
      <ul className="flex flex-col gap-2">
        {notes.map((note) => (
          <li
            key={note.id}
            className="rounded-md bg-muted/40 px-3 py-2 text-sm"
          >
            <p>{note.body}</p>
            <p className="mt-1 text-xs text-muted-foreground">
              {note.source} · {formatCrmTimestamp(note.created_at)}
            </p>
          </li>
        ))}
      </ul>
    </div>
  );
}
