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
import { FunilPanel, type CreateDealPayload } from "./FunilPanel";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ApiError } from "@/lib/api";
import {
  archiveDeal,
  createDeal,
  createNote,
  listCompanies,
  listContacts,
  listDealStages,
  listDeals,
  listNotes,
  moveDeal,
  resolveNotesTarget,
  updateDeal,
  type CrmCompany,
  type CrmContact,
  type CrmDeal,
  type CrmNote,
  type CrmUiTab,
} from "@/lib/crm";
import { suggestFollowupDraft } from "@/lib/crm-next-best-action";
import { isStale } from "@/lib/crm-stagnation";

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
  const [noteBody, setNoteBody] = useState("");
  const [lastNoteAtByDealId, setLastNoteAtByDealId] = useState<
    Record<string, string | null>
  >({});

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

  useEffect(() => {
    // `GET /api/crm/notes` exige exatamente um alvo — não há listagem
    // agregada. Fan-out paralelo por deal para alimentar `isStale`
    // (notes[0] é a mais recente). Sem isso o badge cairia só em
    // `created_at` e marcaria deals ativos como estagnados.
    if (tab !== "pipeline" || deals.length === 0) return;
    let cancelled = false;
    void (async () => {
      const entries = await Promise.all(
        deals.map(async (deal) => {
          try {
            const dealNotes = await listNotes({ deal_id: deal.id });
            return [deal.id, dealNotes[0]?.created_at ?? null] as const;
          } catch {
            return [deal.id, null] as const;
          }
        })
      );
      if (!cancelled) {
        setLastNoteAtByDealId(Object.fromEntries(entries));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [tab, deals]);

  // Handler de criar lead — recebe os campos já resolvidos pelo
  // FunilPanel (form interno). Encaminha `contact` aninhado, grava
  // descrição/indicação como nota inicial e recarrega via `refreshShared`.
  const onCreateDeal = async (payload: CreateDealPayload) => {
    if (!payload.title.trim()) return;
    try {
      const created = await createDeal({
        title: payload.title,
        stage: payload.stage,
        contact_id: payload.contactId,
        company_id: payload.companyId,
        value: payload.value.trim() ? payload.value.trim() : null,
        currency: payload.value.trim() ? "BRL" : null,
        contact: payload.contact,
      });
      const referrer = payload.referredByContactId
        ? contacts.find((c) => c.id === payload.referredByContactId)
        : undefined;
      const noteParts: string[] = [];
      if (payload.description?.trim()) {
        noteParts.push(payload.description.trim());
      }
      if (referrer) {
        noteParts.push(`Indicado por: ${referrer.name}`);
      } else if (payload.referredByContactId) {
        noteParts.push(`Indicado por contato ${payload.referredByContactId}`);
      }
      if (noteParts.length > 0) {
        await createNote({
          body: noteParts.join("\n\n"),
          source: "user",
          deal_id: created.id,
        });
      }
      await refreshShared();
      setSelectedContactId(null);
      setSelectedCompanyId(null);
      setSelectedDealId(created.id);
      setTab("pipeline");
      toast.success("Lead criado");
    } catch (err) {
      setError(errMessage(err));
    }
  };

  const onUpdateDeal = async (payload: CreateDealPayload) => {
    if (!selectedDealId || !payload.title.trim()) return;
    try {
      await updateDeal(selectedDealId, {
        title: payload.title,
        stage: payload.stage,
        company_id: payload.companyId,
        clear_company: payload.companyId == null,
        value: payload.value.trim() ? payload.value.trim() : null,
        currency: payload.value.trim() ? "BRL" : null,
        contact: payload.contact,
      });
      const referrer = payload.referredByContactId
        ? contacts.find((c) => c.id === payload.referredByContactId)
        : undefined;
      if (referrer) {
        const already = notes.some(
          (note) => note.body === `Indicado por: ${referrer.name}`
        );
        if (!already) {
          await createNote({
            body: `Indicado por: ${referrer.name}`,
            source: "user",
            deal_id: selectedDealId,
          });
        }
      }
      await refreshShared();
      toast.success("Lead atualizado");
    } catch (err) {
      setError(errMessage(err));
    }
  };

  const onMoveDeal = async (dealId: string, stage: string) => {
    try {
      const updated = await moveDeal(dealId, stage);
      setDeals((prev) => prev.map((d) => (d.id === updated.id ? updated : d)));
      setLastNoteAtByDealId((prev) => ({
        ...prev,
        [dealId]: new Date().toISOString(),
      }));
      toast.success(`Deal movido para ${stage}`);
    } catch (err) {
      setError(errMessage(err));
    }
  };

  const onArchiveDeal = async () => {
    if (!selectedDealId) return;
    try {
      await archiveDeal(selectedDealId);
      setDeals((prev) => prev.filter((d) => d.id !== selectedDealId));
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
      if (selectedDealId) {
        setLastNoteAtByDealId((prev) => ({
          ...prev,
          [selectedDealId]: created.created_at,
        }));
        toast.success("Nota adicionada");
      }
    } catch (err) {
      setError(errMessage(err));
    }
  };

  const followupSuggestion = useMemo(() => {
    if (!selectedDealId) return null;
    const deal = deals.find((d) => d.id === selectedDealId);
    if (!deal) return null;
    const lastNoteAt = lastNoteAtByDealId[deal.id] ?? null;
    if (!isStale(deal, lastNoteAt)) return null;
    return { editable_text: suggestFollowupDraft(notes) };
  }, [selectedDealId, deals, lastNoteAtByDealId, notes]);

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
            <FunilPanel
              deals={deals}
              stages={stages}
              contacts={contacts}
              companies={companies}
              selectedDealId={selectedDealId}
              onSelectDeal={(id) => {
                setSelectedDealId(id);
                setSelectedContactId(null);
                setSelectedCompanyId(null);
              }}
              notes={notes}
              noteBody={noteBody}
              setNoteBody={setNoteBody}
              onAddNote={onAddNote}
              onCreateDeal={onCreateDeal}
              onUpdateDeal={onUpdateDeal}
              onMoveDeal={onMoveDeal}
              onArchiveDeal={onArchiveDeal}
              lastNoteAtByDealId={lastNoteAtByDealId}
              followupSuggestion={followupSuggestion}
              onConfirmFollowup={async (draft) => {
                if (!selectedDealId) return;
                try {
                  const created = await createNote({
                    body: draft,
                    source: "user",
                    deal_id: selectedDealId,
                  });
                  setNotes((prev) => [created, ...prev]);
                  setLastNoteAtByDealId((prev) => ({
                    ...prev,
                    [selectedDealId]: created.created_at,
                  }));
                  toast.success("Follow-up registrado");
                } catch (err) {
                  setError(errMessage(err));
                }
              }}
              onDealsChanged={() => {
                refreshShared().catch((err) => setError(errMessage(err)));
              }}
            />
          </TabsContent>
        </Tabs>
      </main>
    </div>
  );
}
