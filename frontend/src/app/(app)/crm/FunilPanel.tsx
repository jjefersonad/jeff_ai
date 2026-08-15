"use client";

/**
 * Aba Funil — toggle Kanban/Lista (REQ-001 sales-kanban-frontend,
 * sales-pipeline-via-agent-task-frontend-funil-1) + base do Kanban
 * (que já existia em `crm/page.tsx` antes desta extração).
 *
 * Estado interno `view: "kanban" | "list"` controla qual visualização
 * renderiza. O toggle é LOCAL — NÃO muda rota, NÃO chama
 * `next/router` push, NÃO usa URL. Por design, o funil é uma
 * visualização de leitura, não uma navegação: o usuário pode alternar
 * entre Kanban e Lista sem perder o deal selecionado nem o estado do
 * formulário de criar.
 *
 * Detalhes do deal selecionado abrem num drawer lateral (overlay +
 * painel `fixed right-0`) compartilhado entre Kanban e Lista.
 * frontend-funil-2 adiciona drag-and-drop nas
 * colunas (chama `onMoveDeal` → `POST /api/crm/deals/{id}/move`)
 * e o badge `"estagnado Nd"` via `isStale` (espelho do `is_stale`
 * Python). frontend-funil-3 trava a vista Lista (tabela Título/
 * Contato/Empresa/Valor/Estágio/Atualizado + header busca/Adicionar
 * no padrão Empresas). frontend-funil-4 troca a section abaixo
 * do Kanban por esse drawer com timeline de `crm_notes`
 * (REQ-003: `created_at DESC` + indicador de `source`). frontend-funil-5
 * adiciona ações inline no drawer: dropdown de estágio (chama
 * `onMoveDeal` → `POST /api/crm/deals/{id}/move`), textarea + Salvar
 * (grava `crm_notes`), e modal de follow-up pré-preenchido quando
 * há sugestão de `next_best_action`. frontend-funil-6 adiciona a
 * seção "Sugestão do agente" no topo do drawer (usar | editar |
 * ignorar). frontend-funil-7 (REQ-006): nenhum `Tier3ApprovalDialog`
 * novo — o modal de follow-up é composição, não gate de aprovação.
 * Tools do funil (`crm_move_deal`, `request_followup`, `add_deal_note`)
 * estão em `TIER_2_TOOLS` (executam direto). No chat, interrupts
 * continuam no `ToolApprovalInterrupt` já existente (`ChatInterface` /
 * `ToolCallBox`). Na UI do CRM, a notificação é o mesmo `toast` das
 * outras abas.
 */

import {
  type DragEvent,
  type FormEvent,
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react";

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
import { Textarea } from "@/components/ui/textarea";
import { daysSinceActivity, isStale } from "@/lib/crm-stagnation";
import {
  dealStageLabel,
  formatCrmTimestamp,
  formatDealValue,
  type CrmCompany,
  type CrmContact,
  type CrmDeal,
  type CrmNote,
} from "@/lib/crm";

type FunilView = "kanban" | "list";
type EditorMode = "closed" | "create" | "edit";

/**
 * Payload do handler de criar/editar lead (callback de `FunilPanel`
 * para o `page.tsx`). Cadastro e edição abrem no mesmo drawer
 * lateral; "Criar"/"Salvar" resolve os campos e chama o callback.
 * `contact` só vai no payload quando há e-mail ou telefone (o CHECK
 * de `crm_contacts` exige um identificador). `referredByContactId` é
 * quem indicou o lead — não é o contato do próprio card.
 */
export type CreateDealContactPayload = {
  name?: string;
  email?: string;
  phone?: string;
  city?: string;
  state?: string;
  tags?: string[];
};

export type CreateDealPayload = {
  title: string;
  stage: string;
  value: string;
  currency: string;
  contactId: string | null;
  referredByContactId: string | null;
  companyId: string | null;
  description?: string;
  contact?: CreateDealContactPayload;
};

function parseTagList(raw: string): string[] {
  return raw
    .split(",")
    .map((tag) => tag.trim())
    .filter(Boolean);
}

function buildLeadContactPayload(fields: {
  name: string;
  email: string;
  phone: string;
  city: string;
  state: string;
  tags: string;
}): CreateDealContactPayload | undefined {
  const name = fields.name.trim();
  const email = fields.email.trim();
  const phone = fields.phone.trim();
  if (!email && !phone) return undefined;
  const city = fields.city.trim();
  const state = fields.state.trim();
  const tags = parseTagList(fields.tags);
  return {
    name,
    ...(email ? { email } : {}),
    ...(phone ? { phone } : {}),
    ...(city ? { city } : {}),
    ...(state ? { state } : {}),
    ...(tags.length > 0 ? { tags } : {}),
  };
}

type Props = {
  deals: CrmDeal[];
  stages: string[];
  contacts: CrmContact[];
  companies: CrmCompany[];
  selectedDealId: string | null;
  onSelectDeal: (id: string | null) => void;
  notes: CrmNote[];
  noteBody: string;
  setNoteBody: (value: string) => void;
  onAddNote: (event: FormEvent) => void | Promise<void>;
  onCreateDeal: (payload: CreateDealPayload) => void | Promise<void>;
  onUpdateDeal?: (payload: CreateDealPayload) => void | Promise<void>;
  onMoveDeal: (dealId: string, stage: string) => void | Promise<void>;
  onArchiveDeal: () => void | Promise<void>;
  onDealsChanged?: () => void;
  /**
   * Timestamp ISO da `crm_notes` mais recente por deal. Ausente ou
   * `null` ⇒ `isStale` cai em `deal.created_at` (mesmo contrato do
   * backend). Page.tsx preenche isso listando notas por deal.
   */
  lastNoteAtByDealId?: Record<string, string | null>;
  /**
   * Rascunho de `next_best_action.suggest()` para o deal aberto.
   * Ausente/`null` ⇒ o modal de follow-up abre em branco (REQ-004:
   * o usuário ainda pode compor manualmente).
   */
  followupSuggestion?: { editable_text: string } | null;
  onConfirmFollowup?: (draft: string) => void | Promise<void>;
};

export function FunilPanel({
  deals,
  stages,
  contacts,
  companies,
  selectedDealId,
  onSelectDeal,
  notes,
  noteBody,
  setNoteBody,
  onAddNote,
  onCreateDeal,
  onUpdateDeal,
  onMoveDeal,
  onArchiveDeal,
  lastNoteAtByDealId = {},
  followupSuggestion = null,
  onConfirmFollowup,
}: Props) {
  const [view, setView] = useState<FunilView>("kanban");
  const [followupOpen, setFollowupOpen] = useState(false);
  const [followupDraft, setFollowupDraft] = useState("");
  const [suggestionDismissed, setSuggestionDismissed] = useState(false);
  const [searchDraft, setSearchDraft] = useState("");
  const [query, setQuery] = useState("");

  // Form state do "Novo Lead" — cadastro e edição abrem no mesmo
  // drawer lateral. Kanban e Lista compartilham este único formulário.
  const [leadName, setLeadName] = useState("");
  const [leadEmail, setLeadEmail] = useState("");
  const [leadPhone, setLeadPhone] = useState("");
  const [leadDescription, setLeadDescription] = useState("");
  const [leadCity, setLeadCity] = useState("");
  const [leadState, setLeadState] = useState("");
  const [leadTags, setLeadTags] = useState("");
  const [referredByContactId, setReferredByContactId] = useState("none");
  const [dealLinkCompanyId, setDealLinkCompanyId] = useState<string>("none");
  const [dealStage, setDealStage] = useState(stages[0] ?? "lead");
  const [dealValue, setDealValue] = useState("");
  const [editorMode, setEditorMode] = useState<EditorMode>("closed");

  const selectedDeal = useMemo(
    () => deals.find((d) => d.id === selectedDealId) ?? null,
    [deals, selectedDealId]
  );

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

  const filteredDeals = useMemo(() => {
    if (!query) return deals;
    const q = query.toLowerCase();
    return deals.filter((deal) => {
      if (deal.title.toLowerCase().includes(q)) return true;
      const contact = contacts.find((c) => c.id === deal.contact_id);
      if (contact?.name.toLowerCase().includes(q)) return true;
      const company = companies.find((c) => c.id === deal.company_id);
      if (company?.name.toLowerCase().includes(q)) return true;
      return false;
    });
  }, [deals, contacts, companies, query]);

  const handleSelect = useCallback(
    (id: string) => {
      onSelectDeal(id);
    },
    [onSelectDeal]
  );

  const handleToggleView = useCallback((next: FunilView) => {
    setView(next);
  }, []);

  const handleCardDragStart = useCallback(
    (event: DragEvent<HTMLButtonElement>, dealId: string, stage: string) => {
      event.dataTransfer.effectAllowed = "move";
      event.dataTransfer.setData("application/x-deal-id", dealId);
      event.dataTransfer.setData("text/plain", dealId);
      event.dataTransfer.setData("application/x-deal-stage", stage);
    },
    []
  );

  const handleColumnDragOver = useCallback(
    (event: DragEvent<HTMLDivElement>) => {
      event.preventDefault();
      event.dataTransfer.dropEffect = "move";
    },
    []
  );

  const handleColumnDrop = useCallback(
    (event: DragEvent<HTMLDivElement>, stage: string) => {
      event.preventDefault();
      const dealId =
        event.dataTransfer.getData("application/x-deal-id") ||
        event.dataTransfer.getData("text/plain");
      const fromStage = event.dataTransfer.getData("application/x-deal-stage");
      if (!dealId || fromStage === stage) return;
      void onMoveDeal(dealId, stage);
    },
    [onMoveDeal]
  );

  const handleCloseDrawer = useCallback(() => {
    setEditorMode("closed");
    onSelectDeal(null);
    setFollowupOpen(false);
    setLeadName("");
    setLeadEmail("");
    setLeadPhone("");
    setLeadDescription("");
    setLeadCity("");
    setLeadState("");
    setLeadTags("");
    setReferredByContactId("none");
    setDealLinkCompanyId("none");
    setDealStage(stages[0] ?? "lead");
    setDealValue("");
  }, [onSelectDeal, stages]);

  const handleOpenFollowup = useCallback(() => {
    setFollowupDraft(followupSuggestion?.editable_text ?? "");
    setFollowupOpen(true);
  }, [followupSuggestion]);

  const handleDismissSuggestion = useCallback(() => {
    setSuggestionDismissed(true);
  }, []);

  const handleConfirmFollowup = useCallback(async () => {
    const text = followupDraft.trim();
    if (!text) return;
    await onConfirmFollowup?.(text);
    setFollowupOpen(false);
  }, [followupDraft, onConfirmFollowup]);

  const openCreateForm = useCallback(() => {
    onSelectDeal(null);
    setLeadName("");
    setLeadEmail("");
    setLeadPhone("");
    setLeadDescription("");
    setLeadCity("");
    setLeadState("");
    setLeadTags("");
    setReferredByContactId("none");
    setDealLinkCompanyId("none");
    setDealStage(stages[0] ?? "lead");
    setDealValue("");
    setEditorMode("create");
  }, [onSelectDeal, stages]);

  const submitLeadForm = useCallback(
    (event: FormEvent) => {
      event.preventDefault();
      const name = leadName.trim();
      if (!name) return;
      const description = leadDescription.trim();
      const contact = buildLeadContactPayload({
        name,
        email: leadEmail,
        phone: leadPhone,
        city: leadCity,
        state: leadState,
        tags: leadTags,
      });
      const payload: CreateDealPayload = {
        title: name,
        stage: dealStage,
        value: dealValue,
        currency: "BRL",
        contactId: null,
        referredByContactId:
          referredByContactId !== "none" ? referredByContactId : null,
        companyId: dealLinkCompanyId !== "none" ? dealLinkCompanyId : null,
        ...(editorMode === "create" && description ? { description } : {}),
        ...(contact ? { contact } : {}),
      };
      if (editorMode === "create") {
        void onCreateDeal(payload);
        return;
      }
      void onUpdateDeal?.(payload);
    },
    [
      leadName,
      leadEmail,
      leadPhone,
      leadCity,
      leadState,
      leadTags,
      leadDescription,
      dealStage,
      dealValue,
      referredByContactId,
      dealLinkCompanyId,
      editorMode,
      onCreateDeal,
      onUpdateDeal,
    ]
  );

  const handleStageChange = useCallback(
    (stage: string) => {
      setDealStage(stage);
      if (
        editorMode === "edit" &&
        selectedDeal &&
        stage !== String(selectedDeal.stage)
      ) {
        void onMoveDeal(selectedDeal.id, stage);
      }
    },
    [editorMode, selectedDeal, onMoveDeal]
  );

  useEffect(() => {
    if (!selectedDealId) return;
    const deal = deals.find((item) => item.id === selectedDealId);
    if (!deal) return;
    const contact = deal.contact_id
      ? (contacts.find((item) => item.id === deal.contact_id) ?? null)
      : null;
    setEditorMode("edit");
    setLeadName(deal.title);
    setLeadEmail(contact?.email ?? "");
    setLeadPhone(contact?.phone ?? "");
    setLeadDescription("");
    setLeadCity(contact?.city ?? "");
    setLeadState(contact?.state ?? "");
    setLeadTags((contact?.tags ?? []).join(", "));
    setReferredByContactId("none");
    setDealLinkCompanyId(deal.company_id ?? "none");
    setDealStage(String(deal.stage));
    setDealValue(deal.value != null ? String(deal.value) : "");
  }, [selectedDealId, deals, contacts]);

  useEffect(() => {
    if (!selectedDealId && editorMode === "edit") {
      setEditorMode("closed");
    }
  }, [selectedDealId, editorMode]);

  useEffect(() => {
    setSuggestionDismissed(false);
  }, [selectedDealId]);

  useEffect(() => {
    if (editorMode === "closed") return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") handleCloseDrawer();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [editorMode, handleCloseDrawer]);

  return (
    <div className="flex flex-col gap-4">
      {/*
        Header da visualização — toggle Kanban/Lista (REQ-001).
        O toggle é LOCAL: `useState` interno. Não mexe em URL, não
        chama router, não é persistido. No Kanban, Adicionar fica à
        direita (mesmo padrão de Contatos/Empresas) e abre o drawer.
      */}
      <div className="flex items-center gap-2 border-b border-border">
        <div
          role="tablist"
          aria-label="Visualização do funil"
          className="flex items-center gap-2"
        >
          <button
            type="button"
            role="tab"
            aria-selected={view === "kanban"}
            aria-label="Visualização Kanban"
            onClick={() => handleToggleView("kanban")}
            className={`-mb-px border-b-2 px-3 py-2 text-sm ${
              view === "kanban"
                ? "border-primary font-medium"
                : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            Kanban
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={view === "list"}
            aria-label="Visualização Lista"
            onClick={() => handleToggleView("list")}
            className={`-mb-px border-b-2 px-3 py-2 text-sm ${
              view === "list"
                ? "border-primary font-medium"
                : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            Lista
          </button>
        </div>
        {view === "kanban" ? (
          <Button
            type="button"
            className="sm:ml-auto"
            onClick={openCreateForm}
          >
            Adicionar
          </Button>
        ) : null}
      </div>

      {view === "kanban" ? (
        <div
          role="tabpanel"
          aria-label="Kanban do funil"
          className="grid gap-3 md:grid-cols-2 xl:grid-cols-6"
        >
          {stages.map((stage) => (
            <div
              key={stage}
              role="group"
              aria-label={`Coluna ${dealStageLabel(stage)}`}
              className="flex min-h-[200px] flex-col gap-2 rounded-md border border-border p-3"
              onDragOverCapture={handleColumnDragOver}
              onDrop={(event) => handleColumnDrop(event, stage)}
            >
              <h3 className="text-sm font-semibold">{dealStageLabel(stage)}</h3>
              {(dealsByStage[stage] ?? []).map((deal) => {
                const contact = contacts.find((c) => c.id === deal.contact_id);
                const lastNoteAt = lastNoteAtByDealId[deal.id] ?? null;
                const stale = isStale(deal, lastNoteAt);
                const formattedValue = formatDealValue(deal.value, deal.currency);
                return (
                <button
                  key={deal.id}
                  type="button"
                  draggable
                  className={`rounded-md border border-border px-2 py-2 text-left text-sm hover:bg-accent ${
                    selectedDealId === deal.id ? "bg-accent" : ""
                  }`}
                  onDragStart={(event) =>
                    handleCardDragStart(event, deal.id, stage)
                  }
                  onClick={() => handleSelect(deal.id)}
                >
                  <span className="font-medium">{deal.title}</span>
                  {contact && (
                    <span className="mt-1 block text-xs text-muted-foreground">
                      {contact.name}
                    </span>
                  )}
                  {formattedValue && (
                    <span className="mt-1 block text-xs text-muted-foreground">
                      {formattedValue}
                    </span>
                  )}
                  {stale && (
                    <span className="mt-1 inline-block rounded bg-amber-500/15 px-1.5 py-0.5 text-xs font-medium text-amber-800 dark:text-amber-300">
                      {`estagnado ${daysSinceActivity(deal, lastNoteAt)}d`}
                    </span>
                  )}
                </button>
                );
              })}
            </div>
          ))}
        </div>
      ) : (
        <div
          role="tabpanel"
          aria-label="Lista do funil"
          className="flex flex-col gap-3"
        >
          {/*
            Lista: busca à esquerda e Adicionar à direita, mesmo
            padrão de Contatos/Empresas. Adicionar abre o drawer de
            cadastro (o mesmo do Kanban).
          */}
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
            <Input
              placeholder="Buscar deals por título, contato ou empresa"
              value={searchDraft}
              onChange={(e) => setSearchDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") setQuery(searchDraft.trim());
              }}
              aria-label="Buscar deals"
              className="sm:max-w-sm"
            />
            <Button
              type="button"
              variant="secondary"
              onClick={() => setQuery(searchDraft.trim())}
            >
              Buscar
            </Button>
            <Button
              type="button"
              className="sm:ml-auto"
              onClick={openCreateForm}
            >
              Adicionar
            </Button>
          </div>

          {filteredDeals.length === 0 ? (
            <p className="rounded-md border border-dashed border-border p-6 text-center text-sm text-muted-foreground">
              Nenhum deal encontrado.
            </p>
          ) : (
            <div className="overflow-x-auto rounded-md border border-border">
              <table className="w-full text-sm">
                <thead className="border-b border-border bg-muted/40 text-left">
                  <tr>
                    <th className="px-3 py-2 font-medium">Título</th>
                    <th className="px-3 py-2 font-medium">Contato</th>
                    <th className="px-3 py-2 font-medium">Empresa</th>
                    <th className="px-3 py-2 font-medium">Valor</th>
                    <th className="px-3 py-2 font-medium">Estágio</th>
                    <th className="px-3 py-2 font-medium">Atualizado</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredDeals.map((deal) => {
                    const contact = contacts.find(
                      (c) => c.id === deal.contact_id
                    );
                    const company = companies.find(
                      (c) => c.id === deal.company_id
                    );
                    return (
                      <tr
                        key={deal.id}
                        className={`cursor-pointer border-b border-border last:border-0 hover:bg-accent ${
                          selectedDealId === deal.id ? "bg-accent/50" : ""
                        }`}
                        onClick={() => handleSelect(deal.id)}
                      >
                        <td className="px-3 py-2 font-medium">{deal.title}</td>
                        <td className="px-3 py-2 text-muted-foreground">
                          {contact?.name ?? "—"}
                        </td>
                        <td className="px-3 py-2 text-muted-foreground">
                          {company?.name ?? "—"}
                        </td>
                        <td className="px-3 py-2 text-muted-foreground">
                          {formatDealValue(deal.value, deal.currency) ?? "—"}
                        </td>
                        <td className="px-3 py-2 text-muted-foreground">
                          {dealStageLabel(String(deal.stage))}
                        </td>
                        <td className="px-3 py-2 text-muted-foreground">
                          {formatCrmTimestamp(deal.updated_at)}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {editorMode !== "closed" ? (
        <>
          <div
            aria-hidden="true"
            data-testid="deal-drawer-backdrop"
            onClick={handleCloseDrawer}
            className="fixed inset-0 z-40 bg-black/50"
          />
          <aside
            data-testid="deal-drawer"
            role="dialog"
            aria-modal="true"
            aria-label={
              editorMode === "create"
                ? "Novo Lead"
                : `Deal ${selectedDeal?.title ?? leadName}`
            }
            className="fixed inset-y-0 right-0 z-50 flex w-[85vw] max-w-md flex-col overflow-y-auto border-l border-border bg-background p-4 shadow-lg"
          >
            <div className="flex items-start justify-between gap-3">
              <h2 className="font-medium">
                {editorMode === "create" ? "Novo Lead" : leadName || "Lead"}
              </h2>
              <Button
                type="button"
                variant="ghost"
                onClick={handleCloseDrawer}
              >
                Fechar
              </Button>
            </div>
            {editorMode === "edit" &&
            followupSuggestion &&
            !suggestionDismissed ? (
              <section
                aria-label="Sugestão do agente"
                className="mt-3 rounded-md border border-border bg-muted/40 p-3"
              >
                <h3 className="text-sm font-medium">Sugestão do agente</h3>
                <p className="mt-1 text-sm text-muted-foreground">
                  {followupSuggestion.editable_text}
                </p>
                <div className="mt-2 flex flex-wrap gap-2">
                  <Button
                    type="button"
                    size="sm"
                    onClick={handleOpenFollowup}
                  >
                    usar
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    onClick={handleOpenFollowup}
                  >
                    editar
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    onClick={handleDismissSuggestion}
                  >
                    ignorar
                  </Button>
                </div>
              </section>
            ) : null}
            <form
              aria-label={
                editorMode === "create"
                  ? "Formulário de criação de lead"
                  : "Formulário de edição de lead"
              }
              onSubmit={submitLeadForm}
              className="mt-3 flex flex-col gap-3"
            >
              <div className="flex flex-col gap-1">
                <Label htmlFor="lead-name">Nome *</Label>
                <Input
                  id="lead-name"
                  required
                  value={leadName}
                  onChange={(e) => setLeadName(e.target.value)}
                />
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="flex flex-col gap-1">
                  <Label htmlFor="lead-email">E-mail</Label>
                  <Input
                    id="lead-email"
                    type="email"
                    value={leadEmail}
                    onChange={(e) => setLeadEmail(e.target.value)}
                  />
                </div>
                <div className="flex flex-col gap-1">
                  <Label htmlFor="lead-phone">Telefone</Label>
                  <Input
                    id="lead-phone"
                    value={leadPhone}
                    onChange={(e) => setLeadPhone(e.target.value)}
                  />
                </div>
              </div>
              {editorMode === "create" ? (
                <div className="flex flex-col gap-1">
                  <Label htmlFor="lead-description">Descrição</Label>
                  <Textarea
                    id="lead-description"
                    rows={3}
                    placeholder="Descrição inicial da conversa"
                    value={leadDescription}
                    onChange={(e) => setLeadDescription(e.target.value)}
                  />
                </div>
              ) : null}
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="flex flex-col gap-1">
                  <Label htmlFor="lead-city">Cidade</Label>
                  <Input
                    id="lead-city"
                    value={leadCity}
                    onChange={(e) => setLeadCity(e.target.value)}
                  />
                </div>
                <div className="flex flex-col gap-1">
                  <Label htmlFor="lead-state">UF</Label>
                  <Input
                    id="lead-state"
                    value={leadState}
                    onChange={(e) => setLeadState(e.target.value)}
                  />
                </div>
              </div>
              <div className="flex flex-col gap-1">
                <Label htmlFor="lead-tags">Tags</Label>
                <Input
                  id="lead-tags"
                  placeholder="separadas por vírgula"
                  value={leadTags}
                  onChange={(e) => setLeadTags(e.target.value)}
                />
              </div>
              <div className="flex flex-col gap-1">
                <Label htmlFor="lead-referred-by">Contato</Label>
                <Select
                  value={referredByContactId}
                  onValueChange={setReferredByContactId}
                >
                  <SelectTrigger id="lead-referred-by" aria-label="Contato">
                    <SelectValue placeholder="Sem indicação" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">Sem indicação</SelectItem>
                    {contacts
                      .filter((contact) => contact.id !== selectedDeal?.contact_id)
                      .map((contact) => (
                        <SelectItem key={contact.id} value={contact.id}>
                          {contact.name}
                        </SelectItem>
                      ))}
                  </SelectContent>
                </Select>
                <p className="text-xs text-muted-foreground">
                  Opcional. Quem indicou este lead.
                </p>
              </div>
              <div className="flex flex-col gap-1">
                <Label htmlFor="deal-link-company">Empresa</Label>
                <Select
                  value={dealLinkCompanyId}
                  onValueChange={setDealLinkCompanyId}
                >
                  <SelectTrigger
                    id="deal-link-company"
                    aria-label="Empresa"
                    className="h-9 bg-transparent"
                  >
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
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="flex flex-col gap-1">
                  <Label htmlFor="lead-stage">Estágio *</Label>
                  <Select value={dealStage} onValueChange={handleStageChange}>
                    <SelectTrigger
                      id="lead-stage"
                      aria-label={
                        editorMode === "edit" ? "Mover para" : "Estágio"
                      }
                    >
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {stages.map((stage) => (
                        <SelectItem key={stage} value={stage}>
                          {dealStageLabel(stage)}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="flex flex-col gap-1">
                  <Label htmlFor="lead-value">Valor</Label>
                  <Input
                    id="lead-value"
                    type="number"
                    inputMode="decimal"
                    min="0"
                    step="0.01"
                    value={dealValue}
                    onChange={(e) => setDealValue(e.target.value)}
                  />
                </div>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button type="submit">
                  {editorMode === "create" ? "Criar" : "Salvar"}
                </Button>
                {editorMode === "edit" ? (
                  <>
                    <Button
                      type="button"
                      variant="outline"
                      onClick={onArchiveDeal}
                    >
                      Arquivar
                    </Button>
                    <Button
                      type="button"
                      variant="secondary"
                      onClick={handleOpenFollowup}
                    >
                      Enviar follow-up
                    </Button>
                  </>
                ) : (
                  <Button
                    type="button"
                    variant="outline"
                    onClick={handleCloseDrawer}
                  >
                    Cancelar
                  </Button>
                )}
              </div>
            </form>
            {editorMode === "edit" && selectedDeal ? (
              <>
                <dl className="mt-3 grid gap-1 text-xs text-muted-foreground sm:grid-cols-2">
                  <div>
                    <dt>Criado</dt>
                    <dd>{formatCrmTimestamp(selectedDeal.created_at)}</dd>
                  </div>
                  <div>
                    <dt>Atualizado</dt>
                    <dd>{formatCrmTimestamp(selectedDeal.updated_at)}</dd>
                  </div>
                </dl>
                <div className="mt-4">
                  <NotesBlock
                    notes={notes}
                    noteBody={noteBody}
                    setNoteBody={setNoteBody}
                    onAddNote={onAddNote}
                  />
                </div>
              </>
            ) : null}
          </aside>
          <Dialog open={followupOpen} onOpenChange={setFollowupOpen}>
            <DialogContent className="sm:max-w-lg">
              <DialogHeader>
                <DialogTitle>Enviar follow-up</DialogTitle>
                <DialogDescription>
                  Revise o rascunho antes de confirmar. A nota é
                  registrada com origem &quot;você&quot;.
                </DialogDescription>
              </DialogHeader>
              <div className="flex flex-col gap-2">
                <Label htmlFor="deal-followup-draft">Rascunho</Label>
                <Textarea
                  id="deal-followup-draft"
                  value={followupDraft}
                  onChange={(e) => setFollowupDraft(e.target.value)}
                  rows={6}
                />
              </div>
              <DialogFooter>
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setFollowupOpen(false)}
                >
                  Cancelar
                </Button>
                <Button
                  type="button"
                  onClick={() => void handleConfirmFollowup()}
                  disabled={!followupDraft.trim()}
                >
                  Confirmar
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </>
      ) : null}
    </div>
  );
}

function noteSourceLabel(source: string): string {
  if (source === "user") return "você";
  if (source === "agent") return "agente";
  if (source === "system") return "sistema";
  return source;
}

function sortNotesNewestFirst(notes: CrmNote[]): CrmNote[] {
  return [...notes].sort((a, b) => {
    const ta = Date.parse(a.created_at) || 0;
    const tb = Date.parse(b.created_at) || 0;
    return tb - ta;
  });
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
  const timelineNotes = sortNotesNewestFirst(notes);
  return (
    <div className="flex flex-col gap-3 border-t border-border pt-4">
      <h3 className="text-sm font-medium">Timeline</h3>
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
      <ol aria-label="Timeline" className="flex flex-col gap-2">
        {timelineNotes.map((note) => (
          <li
            key={note.id}
            className="rounded-md border border-border px-3 py-2 text-sm"
          >
            <p>{note.body}</p>
            <p className="mt-1 text-xs text-muted-foreground">
              {noteSourceLabel(note.source)} ·{" "}
              {formatCrmTimestamp(note.created_at)}
            </p>
          </li>
        ))}
        {timelineNotes.length === 0 && (
          <li className="text-sm text-muted-foreground">Nenhuma nota ainda.</li>
        )}
      </ol>
    </div>
  );
}
