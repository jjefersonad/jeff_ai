"use client";

/**
 * CRM page — contacts, companies, and deal funnel
 * (extend-crm-fields-location-value-custom).
 */

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { BriefcaseBusiness } from "lucide-react";
import { toast } from "sonner";

import { CompaniesPanel } from "./CompaniesPanel";
import { ContactsPanel } from "./ContactsPanel";
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
  archiveDeal,
  createDeal,
  createNote,
  formatCrmTimestamp,
  listCompanies,
  listContacts,
  listDealStages,
  listDeals,
  listNotes,
  moveDeal,
  resolveNotesTarget,
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
    "qualified",
    "proposal",
    "negotiation",
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

  const [dealTitle, setDealTitle] = useState("");
  const [dealStage, setDealStage] = useState("qualified");
  const [dealValue, setDealValue] = useState("");
  const [dealCurrency, setDealCurrency] = useState("BRL");
  const [dealLinkContactId, setDealLinkContactId] = useState<string>("none");
  const [dealLinkCompanyId, setDealLinkCompanyId] = useState<string>("none");
  const [noteBody, setNoteBody] = useState("");

  const selectedDeal = useMemo(
    () => deals.find((d) => d.id === selectedDealId) ?? null,
    [deals, selectedDealId]
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

  const refreshShared = useCallback(async () => {
    const [c, co, d, st] = await Promise.all([
      listContacts({ page: 1, page_size: 100 }),
      listCompanies(),
      listDeals(),
      listDealStages(),
    ]);
    setContacts(c.items ?? []);
    setCompanies(co);
    setDeals(d);
    if (st.length > 0) setStages(st);
  }, []);

  useEffect(() => {
    refreshShared().catch((err) => setError(errMessage(err)));
  }, [refreshShared]);

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
        value: dealValue.trim() ? dealValue.trim() : null,
        currency: dealValue.trim() ? dealCurrency || "BRL" : null,
      });
      setDeals((prev) => [created, ...prev]);
      setDealTitle("");
      setDealValue("");
      setDealLinkContactId("none");
      setDealLinkCompanyId("none");
      setSelectedContactId(null);
      setSelectedCompanyId(null);
      setSelectedDealId(created.id);
      setTab("pipeline");
      toast.success("Deal criado");
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

        <Tabs value={tab} onValueChange={(value) => setTab(value as TabId)}>
          <TabsList>
            <TabsTrigger value="contacts">Contatos</TabsTrigger>
            <TabsTrigger value="companies">Empresas</TabsTrigger>
            <TabsTrigger value="pipeline">Funil</TabsTrigger>
          </TabsList>

          <TabsContent value="contacts" className="mt-4">
            <ContactsPanel
              companies={companies}
              selectedContactId={selectedContactId}
              onSelectContact={(id) => {
                setSelectedContactId(id);
                setSelectedCompanyId(null);
                setSelectedDealId(null);
              }}
              notes={notes}
              noteBody={noteBody}
              setNoteBody={setNoteBody}
              onAddNote={onAddNote}
              onContactsChanged={() => {
                refreshShared().catch((err) => setError(errMessage(err)));
              }}
            />
          </TabsContent>

          <TabsContent value="companies" className="mt-4">
            <CompaniesPanel
              selectedCompanyId={selectedCompanyId}
              onSelectCompany={(id) => {
                setSelectedCompanyId(id);
                setSelectedContactId(null);
                setSelectedDealId(null);
              }}
              notes={notes}
              noteBody={noteBody}
              setNoteBody={setNoteBody}
              onAddNote={onAddNote}
              onCompaniesChanged={() => {
                refreshShared().catch((err) => setError(errMessage(err)));
              }}
            />
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
              <div className="flex w-32 flex-col gap-1">
                <Label htmlFor="deal-value">Valor</Label>
                <Input
                  id="deal-value"
                  inputMode="decimal"
                  placeholder="0.00"
                  value={dealValue}
                  onChange={(e) => setDealValue(e.target.value)}
                />
              </div>
              <div className="flex w-24 flex-col gap-1">
                <Label htmlFor="deal-currency">Moeda</Label>
                <Input
                  id="deal-currency"
                  value={dealCurrency}
                  onChange={(e) => setDealCurrency(e.target.value)}
                />
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
                      {deal.value != null && (
                        <span className="mt-1 block text-xs text-muted-foreground">
                          {deal.currency ?? "BRL"} {deal.value}
                        </span>
                      )}
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
                <p className="mt-1 text-sm">
                  Valor:{" "}
                  {selectedDeal.value != null
                    ? `${selectedDeal.currency ?? "BRL"} ${selectedDeal.value}`
                    : "—"}
                </p>
                <dl className="mt-2 grid gap-1 text-xs text-muted-foreground sm:grid-cols-2">
                  <div>
                    <dt>Criado</dt>
                    <dd>{formatCrmTimestamp(selectedDeal.created_at)}</dd>
                  </div>
                  <div>
                    <dt>Atualizado</dt>
                    <dd>{formatCrmTimestamp(selectedDeal.updated_at)}</dd>
                  </div>
                </dl>
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
              {note.source} · {formatCrmTimestamp(note.created_at)}
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
