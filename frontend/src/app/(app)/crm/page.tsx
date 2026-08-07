"use client";

/**
 * CRM page — contacts, companies, and deal funnel (add-simple-crm-module).
 *
 * Authenticated shell only (`(app)/crm`). Uses `lib/crm.ts` → `/api/crm/*`.
 */

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { BriefcaseBusiness } from "lucide-react";

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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ApiError } from "@/lib/api";
import {
  archiveCompany,
  archiveContact,
  archiveDeal,
  createCompany,
  createContact,
  createDeal,
  createNote,
  listCompanies,
  listContacts,
  listDealStages,
  listDeals,
  listNotes,
  moveDeal,
  resolveNotesTarget,
  updateCompany,
  updateContact,
  validateContactForm,
  type CrmCompany,
  type CrmContact,
  type CrmDeal,
  type CrmNote,
  type CrmUiTab,
} from "@/lib/crm";

type TabId = CrmUiTab;

function errMessage(err: unknown): string {
  return err instanceof ApiError ? err.message : "Falha inesperada";
}

export default function CrmPage() {
  const [tab, setTab] = useState<TabId>("contacts");
  const [error, setError] = useState<string | null>(null);

  const [contacts, setContacts] = useState<CrmContact[]>([]);
  const [companies, setCompanies] = useState<CrmCompany[]>([]);
  const [deals, setDeals] = useState<CrmDeal[]>([]);
  const [stages, setStages] = useState<string[]>([
    "lead",
    "qualified",
    "proposal",
    "won",
    "lost",
  ]);

  const [selectedContactId, setSelectedContactId] = useState<string | null>(
    null
  );
  const [selectedCompanyId, setSelectedCompanyId] = useState<string | null>(
    null
  );
  const [selectedDealId, setSelectedDealId] = useState<string | null>(null);
  const [notes, setNotes] = useState<CrmNote[]>([]);

  const [contactName, setContactName] = useState("");
  const [contactEmail, setContactEmail] = useState("");
  const [contactPhone, setContactPhone] = useState("");
  const [contactFormError, setContactFormError] = useState<string | null>(null);

  const [companyName, setCompanyName] = useState("");
  const [companyWebsite, setCompanyWebsite] = useState("");

  const [dealTitle, setDealTitle] = useState("");
  const [dealStage, setDealStage] = useState("lead");
  const [dealLinkContactId, setDealLinkContactId] = useState<string>("none");
  const [dealLinkCompanyId, setDealLinkCompanyId] = useState<string>("none");
  const [noteBody, setNoteBody] = useState("");

  const selectedContact = useMemo(
    () => contacts.find((c) => c.id === selectedContactId) ?? null,
    [contacts, selectedContactId]
  );
  const selectedCompany = useMemo(
    () => companies.find((c) => c.id === selectedCompanyId) ?? null,
    [companies, selectedCompanyId]
  );
  const selectedDeal = useMemo(
    () => deals.find((d) => d.id === selectedDealId) ?? null,
    [deals, selectedDealId]
  );

  const companyContacts = useMemo(
    () =>
      selectedCompany
        ? contacts.filter((c) => c.company_id === selectedCompany.id)
        : [],
    [contacts, selectedCompany]
  );

  const selectedDealContact = useMemo(
    () =>
      selectedDeal?.contact_id
        ? (contacts.find((c) => c.id === selectedDeal.contact_id) ?? null)
        : null,
    [contacts, selectedDeal]
  );

  const selectedDealCompany = useMemo(
    () =>
      selectedDeal?.company_id
        ? (companies.find((c) => c.id === selectedDeal.company_id) ?? null)
        : null,
    [companies, selectedDeal]
  );

  const refreshLists = useCallback(async () => {
    const [c, co, d, st] = await Promise.all([
      listContacts(),
      listCompanies(),
      listDeals(),
      listDealStages(),
    ]);
    setContacts(c);
    setCompanies(co);
    setDeals(d);
    if (st.length > 0) setStages(st);
  }, []);

  useEffect(() => {
    refreshLists().catch((err) => setError(errMessage(err)));
  }, [refreshLists]);

  const loadNotesFor = useCallback(
    async (target: {
      contact_id?: string;
      company_id?: string;
      deal_id?: string;
    }) => {
      const list = await listNotes(target);
      setNotes(list);
    },
    []
  );

  useEffect(() => {
    const target = resolveNotesTarget({
      tab,
      contactId: selectedContactId,
      companyId: selectedCompanyId,
      dealId: selectedDealId,
    });
    setNoteBody("");
    if (!target) {
      setNotes([]);
      return;
    }
    loadNotesFor(target).catch((err) => setError(errMessage(err)));
  }, [
    selectedContactId,
    selectedCompanyId,
    selectedDealId,
    tab,
    loadNotesFor,
  ]);

  const onCreateContact = async (event: FormEvent) => {
    event.preventDefault();
    const validation = validateContactForm({
      name: contactName,
      email: contactEmail,
      phone: contactPhone,
    });
    if (!validation.valid) {
      setContactFormError(validation.error ?? "Dados inválidos");
      return;
    }
    setContactFormError(null);
    setError(null);
    try {
      const created = await createContact({
        name: contactName,
        email: contactEmail || null,
        phone: contactPhone || null,
      });
      setContacts((prev) => [created, ...prev]);
      setContactName("");
      setContactEmail("");
      setContactPhone("");
      setSelectedCompanyId(null);
      setSelectedDealId(null);
      setSelectedContactId(created.id);
      setTab("contacts");
    } catch (err) {
      setError(errMessage(err));
    }
  };

  const onSaveContact = async () => {
    if (!selectedContact) return;
    const validation = validateContactForm({
      name: selectedContact.name,
      email: selectedContact.email,
      phone: selectedContact.phone,
    });
    if (!validation.valid) {
      setContactFormError(validation.error ?? "Dados inválidos");
      return;
    }
    setContactFormError(null);
    try {
      const updated = await updateContact(selectedContact.id, {
        name: selectedContact.name,
        email: selectedContact.email,
        phone: selectedContact.phone,
        company_id: selectedContact.company_id,
        clear_company: selectedContact.company_id == null,
      });
      setContacts((prev) =>
        prev.map((c) => (c.id === updated.id ? updated : c))
      );
    } catch (err) {
      setError(errMessage(err));
    }
  };

  const onArchiveContact = async () => {
    if (!selectedContact) return;
    try {
      await archiveContact(selectedContact.id);
      setContacts((prev) => prev.filter((c) => c.id !== selectedContact.id));
      setSelectedContactId(null);
    } catch (err) {
      setError(errMessage(err));
    }
  };

  const onCreateCompany = async (event: FormEvent) => {
    event.preventDefault();
    if (!companyName.trim()) return;
    try {
      const created = await createCompany({
        name: companyName,
        website: companyWebsite || null,
      });
      setCompanies((prev) => [created, ...prev]);
      setCompanyName("");
      setCompanyWebsite("");
      setSelectedContactId(null);
      setSelectedDealId(null);
      setSelectedCompanyId(created.id);
      setTab("companies");
    } catch (err) {
      setError(errMessage(err));
    }
  };

  const onSaveCompany = async () => {
    if (!selectedCompany) return;
    try {
      const updated = await updateCompany(selectedCompany.id, {
        name: selectedCompany.name,
        website: selectedCompany.website,
        domain: selectedCompany.domain,
        phone: selectedCompany.phone,
        notes: selectedCompany.notes,
      });
      setCompanies((prev) =>
        prev.map((c) => (c.id === updated.id ? updated : c))
      );
    } catch (err) {
      setError(errMessage(err));
    }
  };

  const onArchiveCompany = async () => {
    if (!selectedCompany) return;
    try {
      await archiveCompany(selectedCompany.id);
      setCompanies((prev) => prev.filter((c) => c.id !== selectedCompany.id));
      setSelectedCompanyId(null);
    } catch (err) {
      setError(errMessage(err));
    }
  };

  const onCreateDeal = async (event: FormEvent) => {
    event.preventDefault();
    if (!dealTitle.trim()) return;
    const linkContactId =
      dealLinkContactId !== "none" ? dealLinkContactId : null;
    const linkCompanyId =
      dealLinkCompanyId !== "none" ? dealLinkCompanyId : null;
    try {
      const created = await createDeal({
        title: dealTitle,
        stage: dealStage,
        contact_id: linkContactId,
        company_id: linkCompanyId,
      });
      setDeals((prev) => [created, ...prev]);
      setDealTitle("");
      setDealLinkContactId("none");
      setDealLinkCompanyId("none");
      setSelectedContactId(null);
      setSelectedCompanyId(null);
      setSelectedDealId(created.id);
      setTab("pipeline");
    } catch (err) {
      setError(errMessage(err));
    }
  };

  const onMoveDeal = async (dealId: string, stage: string) => {
    try {
      const updated = await moveDeal(dealId, stage);
      setDeals((prev) => prev.map((d) => (d.id === updated.id ? updated : d)));
    } catch (err) {
      setError(errMessage(err));
    }
  };

  const onArchiveDeal = async () => {
    if (!selectedDeal) return;
    try {
      await archiveDeal(selectedDeal.id);
      setDeals((prev) => prev.filter((d) => d.id !== selectedDeal.id));
      setSelectedDealId(null);
    } catch (err) {
      setError(errMessage(err));
    }
  };

  const onAddNote = async (event: FormEvent) => {
    event.preventDefault();
    if (!noteBody.trim()) return;
    const target = resolveNotesTarget({
      tab,
      contactId: selectedContactId,
      companyId: selectedCompanyId,
      dealId: selectedDealId,
    });
    if (!target) return;
    try {
      const created = await createNote({
        body: noteBody,
        source: "user",
        ...target,
      });
      setNotes((prev) => [created, ...prev]);
      setNoteBody("");
    } catch (err) {
      setError(errMessage(err));
    }
  };

  const dealsByStage = useMemo(() => {
    const map: Record<string, CrmDeal[]> = {};
    for (const stage of stages) map[stage] = [];
    for (const deal of deals) {
      const key = String(deal.stage);
      if (!map[key]) map[key] = [];
      map[key].push(deal);
    }
    return map;
  }, [deals, stages]);

  return (
    <div className="min-h-screen bg-background">
      <header className="sticky top-0 z-40 border-b border-border bg-background/80 backdrop-blur-sm">
        <div className="mx-auto flex max-w-6xl items-center gap-3 px-6 py-4">
          <BriefcaseBusiness
            size={24}
            className="text-primary"
            aria-hidden="true"
          />
          <h1 className="text-xl font-semibold">CRM</h1>
        </div>
      </header>

      <main className="mx-auto flex max-w-6xl flex-col gap-6 px-6 py-8">
        {error && (
          <p className="text-sm text-destructive" role="alert">
            {error}
          </p>
        )}

        <Tabs
          value={tab}
          onValueChange={(value) => setTab(value as TabId)}
        >
          <TabsList>
            <TabsTrigger value="contacts">Contatos</TabsTrigger>
            <TabsTrigger value="companies">Empresas</TabsTrigger>
            <TabsTrigger value="pipeline">Funil</TabsTrigger>
          </TabsList>

          <TabsContent value="contacts" className="mt-4">
            <div className="grid gap-6 lg:grid-cols-[280px_1fr]">
              <section className="flex flex-col gap-4">
                <form
                  onSubmit={onCreateContact}
                  className="flex flex-col gap-3 rounded-md border border-border p-3"
                >
                  <h2 className="text-sm font-medium">Novo contato</h2>
                  <div className="flex flex-col gap-1">
                    <Label htmlFor="contact-name">Nome</Label>
                    <Input
                      id="contact-name"
                      value={contactName}
                      onChange={(e) => setContactName(e.target.value)}
                    />
                  </div>
                  <div className="flex flex-col gap-1">
                    <Label htmlFor="contact-email">E-mail</Label>
                    <Input
                      id="contact-email"
                      type="email"
                      value={contactEmail}
                      onChange={(e) => setContactEmail(e.target.value)}
                    />
                  </div>
                  <div className="flex flex-col gap-1">
                    <Label htmlFor="contact-phone">Telefone</Label>
                    <Input
                      id="contact-phone"
                      value={contactPhone}
                      onChange={(e) => setContactPhone(e.target.value)}
                    />
                  </div>
                  {contactFormError && (
                    <p className="text-sm text-destructive" role="alert">
                      {contactFormError}
                    </p>
                  )}
                  <Button type="submit">Criar</Button>
                </form>

                <ul className="flex flex-col gap-1">
                  {contacts.map((contact) => (
                    <li key={contact.id}>
                      <button
                        type="button"
                        className={`w-full rounded-md px-3 py-2 text-left text-sm hover:bg-accent ${
                          selectedContactId === contact.id ? "bg-accent" : ""
                        }`}
                        onClick={() => {
                          setSelectedContactId(contact.id);
                          setSelectedCompanyId(null);
                          setSelectedDealId(null);
                        }}
                      >
                        <span className="font-medium">{contact.name}</span>
                        <span className="block text-xs text-muted-foreground">
                          {contact.email || contact.phone}
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              </section>

              <section className="rounded-md border border-border p-4">
                {selectedContact ? (
                  <div className="flex flex-col gap-4">
                    <h2 className="font-medium">Detalhe</h2>
                    <div className="grid gap-3 sm:grid-cols-2">
                      <div className="flex flex-col gap-1">
                        <Label>Nome</Label>
                        <Input
                          value={selectedContact.name}
                          onChange={(e) =>
                            setContacts((prev) =>
                              prev.map((c) =>
                                c.id === selectedContact.id
                                  ? { ...c, name: e.target.value }
                                  : c
                              )
                            )
                          }
                        />
                      </div>
                      <div className="flex flex-col gap-1">
                        <Label>Empresa</Label>
                        <Select
                          value={selectedContact.company_id ?? "none"}
                          onValueChange={(value) =>
                            setContacts((prev) =>
                              prev.map((c) =>
                                c.id === selectedContact.id
                                  ? {
                                      ...c,
                                      company_id:
                                        value === "none" ? null : value,
                                    }
                                  : c
                              )
                            )
                          }
                        >
                          <SelectTrigger>
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
                      <div className="flex flex-col gap-1">
                        <Label>E-mail</Label>
                        <Input
                          value={selectedContact.email ?? ""}
                          onChange={(e) =>
                            setContacts((prev) =>
                              prev.map((c) =>
                                c.id === selectedContact.id
                                  ? { ...c, email: e.target.value || null }
                                  : c
                              )
                            )
                          }
                        />
                      </div>
                      <div className="flex flex-col gap-1">
                        <Label>Telefone</Label>
                        <Input
                          value={selectedContact.phone ?? ""}
                          onChange={(e) =>
                            setContacts((prev) =>
                              prev.map((c) =>
                                c.id === selectedContact.id
                                  ? { ...c, phone: e.target.value || null }
                                  : c
                              )
                            )
                          }
                        />
                      </div>
                    </div>
                    <div className="flex gap-2">
                      <Button type="button" onClick={onSaveContact}>
                        Salvar
                      </Button>
                      <Button
                        type="button"
                        variant="outline"
                        onClick={onArchiveContact}
                      >
                        Arquivar
                      </Button>
                    </div>

                    <NotesBlock
                      notes={notes}
                      noteBody={noteBody}
                      setNoteBody={setNoteBody}
                      onAddNote={onAddNote}
                    />
                  </div>
                ) : (
                  <p className="text-sm text-muted-foreground">
                    Selecione um contato.
                  </p>
                )}
              </section>
            </div>
          </TabsContent>

          <TabsContent value="companies" className="mt-4">
            <div className="grid gap-6 lg:grid-cols-[280px_1fr]">
              <section className="flex flex-col gap-4">
                <form
                  onSubmit={onCreateCompany}
                  className="flex flex-col gap-3 rounded-md border border-border p-3"
                >
                  <h2 className="text-sm font-medium">Nova empresa</h2>
                  <div className="flex flex-col gap-1">
                    <Label htmlFor="company-name">Nome</Label>
                    <Input
                      id="company-name"
                      value={companyName}
                      onChange={(e) => setCompanyName(e.target.value)}
                    />
                  </div>
                  <div className="flex flex-col gap-1">
                    <Label htmlFor="company-website">Website</Label>
                    <Input
                      id="company-website"
                      value={companyWebsite}
                      onChange={(e) => setCompanyWebsite(e.target.value)}
                    />
                  </div>
                  <Button type="submit">Criar</Button>
                </form>
                <ul className="flex flex-col gap-1">
                  {companies.map((company) => (
                    <li key={company.id}>
                      <button
                        type="button"
                        className={`w-full rounded-md px-3 py-2 text-left text-sm hover:bg-accent ${
                          selectedCompanyId === company.id ? "bg-accent" : ""
                        }`}
                        onClick={() => {
                          setSelectedCompanyId(company.id);
                          setSelectedContactId(null);
                          setSelectedDealId(null);
                        }}
                      >
                        {company.name}
                      </button>
                    </li>
                  ))}
                </ul>
              </section>

              <section className="rounded-md border border-border p-4">
                {selectedCompany ? (
                  <div className="flex flex-col gap-4">
                    <h2 className="font-medium">Detalhe</h2>
                    <div className="flex flex-col gap-1">
                      <Label>Nome</Label>
                      <Input
                        value={selectedCompany.name}
                        onChange={(e) =>
                          setCompanies((prev) =>
                            prev.map((c) =>
                              c.id === selectedCompany.id
                                ? { ...c, name: e.target.value }
                                : c
                            )
                          )
                        }
                      />
                    </div>
                    <div className="flex flex-col gap-1">
                      <Label>Website</Label>
                      <Input
                        value={selectedCompany.website ?? ""}
                        onChange={(e) =>
                          setCompanies((prev) =>
                            prev.map((c) =>
                              c.id === selectedCompany.id
                                ? { ...c, website: e.target.value || null }
                                : c
                            )
                          )
                        }
                      />
                    </div>
                    <div className="flex gap-2">
                      <Button type="button" onClick={onSaveCompany}>
                        Salvar
                      </Button>
                      <Button
                        type="button"
                        variant="outline"
                        onClick={onArchiveCompany}
                      >
                        Arquivar
                      </Button>
                    </div>

                    <div>
                      <h3 className="mb-2 text-sm font-medium">
                        Contatos vinculados
                      </h3>
                      {companyContacts.length === 0 ? (
                        <p className="text-sm text-muted-foreground">
                          Nenhum contato vinculado.
                        </p>
                      ) : (
                        <ul className="flex flex-col gap-1 text-sm">
                          {companyContacts.map((c) => (
                            <li key={c.id}>
                              {c.name}
                              {c.email ? ` · ${c.email}` : ""}
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>

                    <NotesBlock
                      notes={notes}
                      noteBody={noteBody}
                      setNoteBody={setNoteBody}
                      onAddNote={onAddNote}
                    />
                  </div>
                ) : (
                  <p className="text-sm text-muted-foreground">
                    Selecione uma empresa.
                  </p>
                )}
              </section>
            </div>
          </TabsContent>

          <TabsContent value="pipeline" className="mt-4">
            <form
              onSubmit={onCreateDeal}
              className="mb-6 flex flex-wrap items-end gap-3 rounded-md border border-border p-3"
            >
              <div className="flex min-w-[200px] flex-1 flex-col gap-1">
                <Label htmlFor="deal-title">Novo deal</Label>
                <Input
                  id="deal-title"
                  value={dealTitle}
                  onChange={(e) => setDealTitle(e.target.value)}
                />
              </div>
              <div className="flex w-40 flex-col gap-1">
                <Label>Estágio</Label>
                <Select value={dealStage} onValueChange={setDealStage}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {stages.map((stage) => (
                      <SelectItem key={stage} value={stage}>
                        {stage}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="flex w-48 flex-col gap-1">
                <Label>Contato (opcional)</Label>
                <Select
                  value={dealLinkContactId}
                  onValueChange={setDealLinkContactId}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Sem contato" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">Sem contato</SelectItem>
                    {contacts.map((contact) => (
                      <SelectItem key={contact.id} value={contact.id}>
                        {contact.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="flex w-48 flex-col gap-1">
                <Label>Empresa (opcional)</Label>
                <Select
                  value={dealLinkCompanyId}
                  onValueChange={setDealLinkCompanyId}
                >
                  <SelectTrigger>
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
              <Button type="submit">Criar</Button>
            </form>

            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
              {stages.map((stage) => (
                <div
                  key={stage}
                  className="flex min-h-[200px] flex-col gap-2 rounded-md border border-border p-3"
                >
                  <h3 className="text-sm font-semibold capitalize">{stage}</h3>
                  {(dealsByStage[stage] ?? []).map((deal) => (
                    <button
                      key={deal.id}
                      type="button"
                      className={`rounded-md border border-border px-2 py-2 text-left text-sm hover:bg-accent ${
                        selectedDealId === deal.id ? "bg-accent" : ""
                      }`}
                      onClick={() => {
                        setSelectedDealId(deal.id);
                        setSelectedContactId(null);
                        setSelectedCompanyId(null);
                      }}
                    >
                      <span className="font-medium">{deal.title}</span>
                    </button>
                  ))}
                </div>
              ))}
            </div>

            {selectedDeal && (
              <section className="mt-6 rounded-md border border-border p-4">
                <h2 className="font-medium">{selectedDeal.title}</h2>
                <p className="mt-1 text-sm text-muted-foreground">
                  Contato: {selectedDealContact?.name ?? "—"} · Empresa:{" "}
                  {selectedDealCompany?.name ?? "—"}
                </p>
                <div className="mt-3 flex flex-wrap items-center gap-3">
                  <Label>Mover para</Label>
                  <Select
                    value={String(selectedDeal.stage)}
                    onValueChange={(stage) =>
                      onMoveDeal(selectedDeal.id, stage)
                    }
                  >
                    <SelectTrigger className="w-44">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {stages.map((stage) => (
                        <SelectItem key={stage} value={stage}>
                          {stage}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <Button
                    type="button"
                    variant="outline"
                    onClick={onArchiveDeal}
                  >
                    Arquivar
                  </Button>
                </div>
                <div className="mt-4">
                  <NotesBlock
                    notes={notes}
                    noteBody={noteBody}
                    setNoteBody={setNoteBody}
                    onAddNote={onAddNote}
                  />
                </div>
              </section>
            )}
          </TabsContent>
        </Tabs>
      </main>
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
  onAddNote: (event: FormEvent) => void | Promise<void>;
}) {
  return (
    <div className="flex flex-col gap-3 border-t border-border pt-4">
      <h3 className="text-sm font-medium">Notas</h3>
      <form onSubmit={onAddNote} className="flex flex-col gap-2">
        <Textarea
          value={noteBody}
          onChange={(e) => setNoteBody(e.target.value)}
          placeholder="Adicionar nota…"
          rows={3}
        />
        <Button type="submit" className="self-start">
          Adicionar nota
        </Button>
      </form>
      <ul className="flex flex-col gap-2">
        {notes.map((note) => (
          <li
            key={note.id}
            className="rounded-md border border-border px-3 py-2 text-sm"
          >
            <p>{note.body}</p>
            <p className="mt-1 text-xs text-muted-foreground">
              {note.source} · {new Date(note.created_at).toLocaleString()}
            </p>
          </li>
        ))}
        {notes.length === 0 && (
          <li className="text-sm text-muted-foreground">Nenhuma nota ainda.</li>
        )}
      </ul>
    </div>
  );
}
