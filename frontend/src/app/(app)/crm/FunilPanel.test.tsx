/**
 * Tests for the Funil tab Kanban/Lista toggle (frontend-funil-1) and
 * Kanban drag-and-drop + stagnation badge (frontend-funil-2).
 *
 * Unit-1 (REQ-001 sales-kanban-frontend, funil-1): toggling between
 * Kanban and Lista MUST stay within the Funil tab — no route/URL change.
 *
 * Unit-1 (REQ-002 sales-kanban-frontend, funil-2): dropping a card from
 * `proposal` onto `negotiation` MUST call `onMoveDeal` →
 * `POST /api/crm/deals/{id}/move` with the new stage.
 *
 * Unit-2 (REQ-002 sales-kanban-frontend, funil-2): a card where
 * `isStale()=true` with 4 days since the last note MUST render
 * "estagnado 4d".
 *
 * Unit-1 (REQ-001 sales-kanban-frontend, funil-3): Lista table
 * columns [Título, Contato, Empresa, Valor, Estágio, Atualizado]
 * and header search-left / Adicionar-right matching Empresas.
 *
 * Unit-1 (REQ-003 sales-kanban-frontend, funil-4): clicking a card
 * opens a lateral drawer whose timeline lists `crm_notes`
 * newest-first (`created_at DESC`) with distinct source indicators
 * (você / agente / sistema).
 *
 * Unit-1 (REQ-004 sales-kanban-frontend, funil-5): selecting
 * "negotiation" in the drawer stage dropdown MUST call
 * `onMoveDeal` → `POST /api/crm/deals/{id}/move`.
 *
 * Unit-2 (REQ-004 sales-kanban-frontend, funil-5): typing a note
 * and clicking "Salvar" MUST create a `crm_notes` row that appears
 * at the top of the timeline.
 *
 * Unit-1 (REQ-005 sales-kanban-frontend, funil-6): clicking "usar"
 * on the "Sugestão do agente" section MUST open the follow-up modal
 * pre-filled with the suggestion's `editable_text`.
 */
import { type FormEvent, useState } from "react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, act, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { FunilPanel } from "./FunilPanel";
import type { CrmContact, CrmCompany, CrmDeal, CrmNote } from "@/lib/crm";

const mockListDeals = vi.fn();
const mockCreateDeal = vi.fn();
const mockMoveDeal = vi.fn();
const mockArchiveDeal = vi.fn();
const mockListNotes = vi.fn();
const mockCreateNote = vi.fn();
const mockListFieldDefinitions = vi.fn(async () => []);

vi.mock("@/lib/crm", async () => {
  const actual = await vi.importActual<typeof import("@/lib/crm")>("@/lib/crm");
  return {
    ...actual,
    listDeals: (...args: unknown[]) => mockListDeals(...args),
    createDeal: (...args: unknown[]) => mockCreateDeal(...args),
    moveDeal: (...args: unknown[]) => mockMoveDeal(...args),
    archiveDeal: (...args: unknown[]) => mockArchiveDeal(...args),
    listNotes: (...args: unknown[]) => mockListNotes(...args),
    createNote: (...args: unknown[]) => mockCreateNote(...args),
    listFieldDefinitions: (...args: unknown[]) =>
      mockListFieldDefinitions(...args),
  };
});

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

function makeContact(overrides: Partial<CrmContact> = {}): CrmContact {
  return {
    id: "contact-1",
    user_id: "user-1",
    name: "João",
    email: "joao@acme.com",
    phone: null,
    company_id: null,
    status: null,
    tags: [],
    city: null,
    state: null,
    whatsapp_opt_in: false,
    custom_values: {},
    archived_at: null,
    created_at: "2026-08-01T00:00:00Z",
    updated_at: "2026-08-01T00:00:00Z",
    ...overrides,
  };
}

function makeCompany(overrides: Partial<CrmCompany> = {}): CrmCompany {
  return {
    id: "company-1",
    user_id: "user-1",
    name: "Acme",
    website: null,
    domain: null,
    phone: null,
    notes: null,
    city: null,
    state: null,
    custom_values: {},
    archived_at: null,
    created_at: "2026-08-01T00:00:00Z",
    updated_at: "2026-08-01T00:00:00Z",
    ...overrides,
  };
}

function makeDeal(overrides: Partial<CrmDeal> = {}): CrmDeal {
  return {
    id: "deal-1",
    user_id: "user-1",
    title: "Deal A",
    stage: "qualified",
    value: 1000,
    currency: "BRL",
    contact_id: "contact-1",
    company_id: "company-1",
    custom_values: {},
    archived_at: null,
    created_at: "2026-08-01T00:00:00Z",
    updated_at: "2026-08-01T00:00:00Z",
    ...overrides,
  };
}

describe("FunilPanel Kanban/Lista toggle (sales-pipeline-via-agent-task-frontend-funil-1)", () => {
  let originalPushState: typeof window.history.pushState;
  let originalReplaceState: typeof window.history.replaceState;
  const mockPushState = vi.fn();
  const mockReplaceState = vi.fn();

  beforeEach(() => {
    mockListDeals.mockReset();
    mockCreateDeal.mockReset();
    mockMoveDeal.mockReset();
    mockArchiveDeal.mockReset();
    mockListNotes.mockReset();
    mockCreateNote.mockReset();
    mockListFieldDefinitions.mockReset();
    mockListFieldDefinitions.mockResolvedValue([]);
    mockPushState.mockReset();
    mockReplaceState.mockReset();
    mockListDeals.mockResolvedValue([makeDeal()]);
    mockListNotes.mockResolvedValue([]);

    originalPushState = window.history.pushState;
    originalReplaceState = window.history.replaceState;
    window.history.pushState = mockPushState as typeof window.history.pushState;
    window.history.replaceState = mockReplaceState as typeof window.history.replaceState;
  });

  afterEach(() => {
    window.history.pushState = originalPushState;
    window.history.replaceState = originalReplaceState;
  });

  // ----- unit-1 (REQ-001): toggle Lista re-renderiza sem mudar rota/URL -----
  it("unit-1: clicking Lista toggle re-renders the table view without changing the route/URL", () => {
    const pathnameBefore = window.location.pathname;

    render(
      <FunilPanel
        deals={[makeDeal({ id: "deal-1", title: "Acme Co" })]}
        stages={["qualified", "proposal", "negotiation", "won", "lost"]}
        contacts={[makeContact()]}
        companies={[makeCompany()]}
        selectedDealId={null}
        onSelectDeal={() => {}}
        notes={[]}
        noteBody=""
        setNoteBody={() => {}}
        onAddNote={async () => {}}
        onCreateDeal={async () => {}}
        onMoveDeal={async () => {}}
        onArchiveDeal={async () => {}}
        onDealsChanged={() => {}}
      />
    );

    // Estado inicial: Kanban visível. Confirma que o header do Kanban
    // ("Qualificado", "Proposta", ...) está renderizado.
    expect(screen.getByRole("heading", { name: /^Qualificado$/ })).toBeInTheDocument();

    // Clica no toggle "Lista" (aria-label canônico).
    const listaToggle = screen.getByRole("tab", {
      name: /visualização lista/i,
    });
    act(() => {
      fireEvent.click(listaToggle);
    });

    // Vista Lista: agora há um <th>Título</th> na tabela (1 deal seed).
    const titleHeader = screen.getByText("Título", { selector: "th" });
    expect(titleHeader).toBeInTheDocument();

    // A view Kanban anterior sumiu (os títulos de coluna de estágio
    // não estão mais como headings).
    expect(
      screen.queryByRole("heading", { name: /^Qualificado$/ })
    ).not.toBeInTheDocument();

    // O pathname continua o mesmo.
    expect(window.location.pathname).toBe(pathnameBefore);

    // NENHUMA navegação client-side foi disparada.
    expect(mockPushState).not.toHaveBeenCalled();
    expect(mockReplaceState).not.toHaveBeenCalled();
  });
});

/**
 * jsdom's DataTransfer is incomplete; share one store between dragStart
 * and drop so the Kanban can read the deal id / origin stage.
 */
function makeDataTransfer() {
  const store: Record<string, string> = {};
  return {
    dropEffect: "move",
    effectAllowed: "move",
    files: [] as File[],
    items: [] as unknown[],
    types: [] as string[],
    setData(type: string, value: string) {
      store[type] = value;
    },
    getData(type: string) {
      return store[type] ?? "";
    },
    clearData() {
      for (const key of Object.keys(store)) delete store[key];
    },
    setDragImage() {},
  };
}

const FUNIL_STAGES = [
  "lead",
  "qualified",
  "proposal",
  "negotiation",
  "won",
  "lost",
] as const;

type FunilPanelProps = Parameters<typeof FunilPanel>[0];
type ForbiddenLeadProps = Extract<
  keyof FunilPanelProps,
  "leads" | "onConvertLead"
>;
const _noLeadProps: ForbiddenLeadProps extends never ? true : never = true;
void _noLeadProps;

describe("FunilPanel has no lead-triage surface (correct-funil-lead-as-deal-task-frontend-funil-1)", () => {
  it("unit-2: FunilPanel has no leads/onConvertLead props and no triage column", () => {
    render(
      <FunilPanel
        deals={[makeDeal({ id: "deal-1", title: "Acme", stage: "qualified" })]}
        stages={[...FUNIL_STAGES]}
        contacts={[makeContact()]}
        companies={[makeCompany()]}
        selectedDealId={null}
        onSelectDeal={() => {}}
        notes={[]}
        noteBody=""
        setNoteBody={() => {}}
        onAddNote={async () => {}}
        onCreateDeal={async () => {}}
        onMoveDeal={async () => {}}
        onArchiveDeal={async () => {}}
      />
    );

    expect(
      screen.queryByRole("group", { name: /triagem|leads/i })
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /converter/i })
    ).not.toBeInTheDocument();
  });
});

describe("FunilPanel Kanban drag-and-drop (sales-pipeline-via-agent-task-frontend-funil-2)", () => {
  beforeEach(() => {
    mockMoveDeal.mockReset();
    mockMoveDeal.mockResolvedValue(makeDeal({ stage: "negotiation" }));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("unit-1: dropping a card from proposal onto negotiation calls POST /api/crm/deals/{id}/move with the new stage", () => {
    const onMoveDeal = vi.fn(async (dealId: string, stage: string) => {
      await mockMoveDeal(dealId, stage);
    });

    render(
      <FunilPanel
        deals={[
          makeDeal({
            id: "deal-1",
            title: "Acme Proposal",
            stage: "proposal",
          }),
        ]}
        stages={[...FUNIL_STAGES]}
        contacts={[makeContact()]}
        companies={[makeCompany()]}
        selectedDealId={null}
        onSelectDeal={() => {}}
        notes={[]}
        noteBody=""
        setNoteBody={() => {}}
        onAddNote={async () => {}}
        onCreateDeal={async () => {}}
        onMoveDeal={onMoveDeal}
        onArchiveDeal={async () => {}}
      />
    );

    const card = screen.getByRole("button", { name: /acme proposal/i });
    const negotiationColumn = screen.getByRole("group", {
      name: "Coluna Negociação",
    });
    const dataTransfer = makeDataTransfer();

    fireEvent.dragStart(card, { dataTransfer });
    fireEvent.dragOver(negotiationColumn, { dataTransfer });
    fireEvent.drop(negotiationColumn, { dataTransfer });

    expect(onMoveDeal).toHaveBeenCalledWith("deal-1", "negotiation");
    expect(mockMoveDeal).toHaveBeenCalledWith("deal-1", "negotiation");
  });

  it("unit-3: columns are Deal.stage and dropping onto proposal calls onMoveDeal(id, 'proposal')", () => {
    const onMoveDeal = vi.fn(async (dealId: string, stage: string) => {
      await mockMoveDeal(dealId, stage);
    });

    render(
      <FunilPanel
        deals={[
          makeDeal({
            id: "deal-q",
            title: "Acme Qualified",
            stage: "qualified",
          }),
        ]}
        stages={[...FUNIL_STAGES]}
        contacts={[makeContact()]}
        companies={[makeCompany()]}
        selectedDealId={null}
        onSelectDeal={() => {}}
        notes={[]}
        noteBody=""
        setNoteBody={() => {}}
        onAddNote={async () => {}}
        onCreateDeal={async () => {}}
        onMoveDeal={onMoveDeal}
        onArchiveDeal={async () => {}}
      />
    );

    for (const [, label] of [
      ["lead", "Lead"],
      ["qualified", "Qualificado"],
      ["proposal", "Proposta"],
      ["negotiation", "Negociação"],
      ["won", "Ganho"],
      ["lost", "Perdido"],
    ] as const) {
      expect(
        screen.getByRole("group", { name: `Coluna ${label}` })
      ).toBeInTheDocument();
    }

    const card = screen.getByRole("button", { name: /acme qualified/i });
    const proposalColumn = screen.getByRole("group", {
      name: "Coluna Proposta",
    });
    const dataTransfer = makeDataTransfer();

    fireEvent.dragStart(card, { dataTransfer });
    fireEvent.dragOver(proposalColumn, { dataTransfer });
    fireEvent.drop(proposalColumn, { dataTransfer });

    expect(onMoveDeal).toHaveBeenCalledWith("deal-q", "proposal");
  });

  it("unit-2: a stale deal card with 4 days since the last note renders badge text \"estagnado 4d\"", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-08-12T12:00:00.000Z"));

    render(
      <FunilPanel
        deals={[
          makeDeal({
            id: "deal-stale",
            title: "Deal Estagnado",
            stage: "proposal",
            created_at: "2026-07-01T00:00:00Z",
            updated_at: "2026-07-01T00:00:00Z",
          }),
        ]}
        stages={[...FUNIL_STAGES]}
        contacts={[makeContact()]}
        companies={[makeCompany()]}
        selectedDealId={null}
        onSelectDeal={() => {}}
        notes={[]}
        noteBody=""
        setNoteBody={() => {}}
        onAddNote={async () => {}}
        onCreateDeal={async () => {}}
        onMoveDeal={async () => {}}
        onArchiveDeal={async () => {}}
        lastNoteAtByDealId={{ "deal-stale": "2026-08-08T12:00:00.000Z" }}
      />
    );

    expect(screen.getByText("estagnado 4d")).toBeInTheDocument();
  });
});

function renderFunilLista(
  overrides: Partial<Parameters<typeof FunilPanel>[0]> = {}
) {
  const props: Parameters<typeof FunilPanel>[0] = {
    deals: [
      makeDeal({
        id: "deal-1",
        title: "Acme Co",
        stage: "proposal",
        value: 1500,
        currency: "BRL",
        contact_id: "contact-1",
        company_id: "company-1",
        updated_at: "2026-08-10T15:00:00Z",
      }),
    ],
    stages: [...FUNIL_STAGES],
    contacts: [makeContact()],
    companies: [makeCompany()],
    selectedDealId: null,
    onSelectDeal: () => {},
    notes: [],
    noteBody: "",
    setNoteBody: () => {},
    onAddNote: async () => {},
    onCreateDeal: async () => {},
    onMoveDeal: async () => {},
    onArchiveDeal: async () => {},
    ...overrides,
  };
  return render(<FunilPanel {...props} />);
}

describe("FunilPanel Lista view (sales-pipeline-via-agent-task-frontend-funil-3)", () => {
  it("unit-1: Lista table columns and header match the Empresas tab layout", () => {
    renderFunilLista();

    fireEvent.click(
      screen.getByRole("tab", { name: /visualização lista/i })
    );

    const headers = screen.getAllByRole("columnheader").map((th) => th.textContent);
    expect(headers).toEqual([
      "Título",
      "Contato",
      "Empresa",
      "Valor",
      "Estágio",
      "Atualizado",
    ]);

    const searchInput = screen.getByRole("textbox", { name: /buscar deals/i });
    expect(searchInput.tagName).toBe("INPUT");
    expect(searchInput.className).toMatch(/sm:max-w-sm/);

    const addButton = screen.getByRole("button", { name: /^adicionar$/i });
    expect(addButton.className).toMatch(/sm:ml-auto/);

    const headerRow = searchInput.closest("div.flex");
    expect(headerRow).not.toBeNull();
    expect(headerRow!.className).toMatch(/sm:flex-row/);
    expect(headerRow!.className).toMatch(/sm:items-center/);
    expect(headerRow!.contains(addButton)).toBe(true);

    // Input is a direct child of the header row (same as EmpresasPanel).
    expect(headerRow!.children[0]).toBe(searchInput);
    expect(
      Array.from(headerRow!.children).indexOf(addButton)
    ).toBeGreaterThan(0);

    expect(
      screen.getByRole("button", { name: /^buscar$/i })
    ).toBeInTheDocument();

    const dataRow = screen.getAllByRole("row")[1];
    expect(dataRow).toHaveTextContent("Acme Co");
    expect(dataRow).toHaveTextContent("João");
    expect(dataRow).toHaveTextContent("Acme");
    expect(dataRow).toHaveTextContent("Proposta");
  });
});

function makeNote(overrides: Partial<CrmNote> = {}): CrmNote {
  return {
    id: "note-1",
    user_id: "user-1",
    body: "nota",
    source: "user",
    contact_id: null,
    company_id: null,
    deal_id: "deal-1",
    created_at: "2026-08-10T10:00:00Z",
    ...overrides,
  };
}

/**
 * Parent-controlled selection, same contract as `crm/page.tsx`:
 * clicking a card calls `onSelectDeal`, which opens the drawer.
 */
function FunilWithSelection(
  props: Omit<Parameters<typeof FunilPanel>[0], "selectedDealId" | "onSelectDeal">
) {
  const [selectedDealId, setSelectedDealId] = useState<string | null>(null);
  return (
    <FunilPanel
      {...props}
      selectedDealId={selectedDealId}
      onSelectDeal={setSelectedDealId}
    />
  );
}

describe("FunilPanel deal drawer timeline (sales-pipeline-via-agent-task-frontend-funil-4)", () => {
  it("unit-1: clicking a card opens a drawer whose timeline lists notes newest-first with distinct source indicators", () => {
    const notes = [
      makeNote({
        id: "note-user",
        body: "qualified → proposal",
        source: "user",
        created_at: "2026-08-10T10:00:00Z",
      }),
      makeNote({
        id: "note-system",
        body: "Email recebido: Proposta v2",
        source: "system",
        created_at: "2026-08-12T10:00:00Z",
      }),
      makeNote({
        id: "note-agent",
        body: "Follow-up enviado",
        source: "agent",
        created_at: "2026-08-11T10:00:00Z",
      }),
    ];

    render(
      <FunilWithSelection
        deals={[
          makeDeal({
            id: "deal-1",
            title: "Acme Proposal",
            stage: "proposal",
          }),
        ]}
        stages={[...FUNIL_STAGES]}
        contacts={[makeContact()]}
        companies={[makeCompany()]}
        notes={notes}
        noteBody=""
        setNoteBody={() => {}}
        onAddNote={async () => {}}
        onCreateDeal={async () => {}}
        onMoveDeal={async () => {}}
        onArchiveDeal={async () => {}}
      />
    );

    expect(screen.queryByTestId("deal-drawer")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /acme proposal/i }));

    const drawer = screen.getByTestId("deal-drawer");
    expect(drawer.className).toMatch(/fixed/);
    expect(drawer.className).toMatch(/right-0/);

    const timeline = within(drawer).getByRole("list", { name: /timeline/i });
    const items = within(timeline).getAllByRole("listitem");
    expect(items).toHaveLength(3);

    expect(items[0]).toHaveTextContent("Email recebido: Proposta v2");
    expect(items[0]).toHaveTextContent("sistema");
    expect(items[1]).toHaveTextContent("Follow-up enviado");
    expect(items[1]).toHaveTextContent("agente");
    expect(items[2]).toHaveTextContent("qualified → proposal");
    expect(items[2]).toHaveTextContent("você");
  });
});

describe("FunilPanel drawer inline actions (sales-pipeline-via-agent-task-frontend-funil-5)", () => {
  beforeEach(() => {
    mockMoveDeal.mockReset();
    mockCreateNote.mockReset();
    mockMoveDeal.mockResolvedValue(makeDeal({ stage: "negotiation" }));
  });

  it("unit-1: selecting negotiation in the drawer stage dropdown calls POST /api/crm/deals/{id}/move", async () => {
    const user = userEvent.setup();
    const onMoveDeal = vi.fn(async (dealId: string, stage: string) => {
      await mockMoveDeal(dealId, stage);
    });

    render(
      <FunilPanel
        deals={[
          makeDeal({
            id: "deal-1",
            title: "Acme Proposal",
            stage: "proposal",
          }),
        ]}
        stages={[...FUNIL_STAGES]}
        contacts={[makeContact()]}
        companies={[makeCompany()]}
        selectedDealId="deal-1"
        onSelectDeal={() => {}}
        notes={[]}
        noteBody=""
        setNoteBody={() => {}}
        onAddNote={async () => {}}
        onCreateDeal={async () => {}}
        onMoveDeal={onMoveDeal}
        onArchiveDeal={async () => {}}
      />
    );

    const drawer = screen.getByTestId("deal-drawer");
    await user.click(within(drawer).getByRole("combobox", { name: /mover para/i }));
    await user.click(
      await screen.findByRole("option", { name: /^Negociação$/ })
    );

    expect(onMoveDeal).toHaveBeenCalledWith("deal-1", "negotiation");
    expect(mockMoveDeal).toHaveBeenCalledWith("deal-1", "negotiation");
  });

  it("unit-2: typing a note and clicking salvar creates a crm_notes row at the top of the timeline", async () => {
    const user = userEvent.setup();
    mockCreateNote.mockResolvedValue(
      makeNote({
        id: "note-new",
        body: "Ligamos hoje de manhã",
        source: "user",
        created_at: "2026-08-12T18:00:00Z",
      })
    );

    function FunilWithNotes() {
      const [notes, setNotes] = useState<CrmNote[]>([
        makeNote({
          id: "note-old",
          body: "qualified → proposal",
          source: "user",
          created_at: "2026-08-10T10:00:00Z",
        }),
      ]);
      const [noteBody, setNoteBody] = useState("");
      const onAddNote = async (event: FormEvent) => {
        event.preventDefault();
        if (!noteBody.trim()) return;
        const created = (await mockCreateNote({
          body: noteBody,
          source: "user",
          deal_id: "deal-1",
        })) as CrmNote;
        setNotes((prev) => [created, ...prev]);
        setNoteBody("");
      };
      return (
        <FunilPanel
          deals={[
            makeDeal({
              id: "deal-1",
              title: "Acme Proposal",
              stage: "proposal",
            }),
          ]}
          stages={[...FUNIL_STAGES]}
          contacts={[makeContact()]}
          companies={[makeCompany()]}
          selectedDealId="deal-1"
          onSelectDeal={() => {}}
          notes={notes}
          noteBody={noteBody}
          setNoteBody={setNoteBody}
          onAddNote={onAddNote}
          onCreateDeal={async () => {}}
          onMoveDeal={async () => {}}
          onArchiveDeal={async () => {}}
        />
      );
    }

    render(<FunilWithNotes />);

    const drawer = screen.getByTestId("deal-drawer");
    await user.type(
      within(drawer).getByPlaceholderText(/adicionar nota/i),
      "Ligamos hoje de manhã"
    );
    await user.click(within(drawer).getByRole("button", { name: /^adicionar nota$/i }));

    expect(mockCreateNote).toHaveBeenCalledWith({
      body: "Ligamos hoje de manhã",
      source: "user",
      deal_id: "deal-1",
    });

    const timeline = within(drawer).getByRole("list", { name: /timeline/i });
    const items = within(timeline).getAllByRole("listitem");
    expect(items[0]).toHaveTextContent("Ligamos hoje de manhã");
    expect(items[1]).toHaveTextContent("qualified → proposal");
  });
});

describe("FunilPanel agent suggestion (sales-pipeline-via-agent-task-frontend-funil-6)", () => {
  it("unit-1: clicking usar on a suggestion opens the follow-up modal pre-filled with editable_text", async () => {
    const user = userEvent.setup();
    const draft =
      "Olá! Passando para dar continuidade à proposta enviada há 3 dias. Podemos conversar sobre os próximos passos?";

    render(
      <FunilPanel
        deals={[
          makeDeal({
            id: "deal-1",
            title: "Acme Proposal",
            stage: "proposal",
          }),
        ]}
        stages={[...FUNIL_STAGES]}
        contacts={[makeContact()]}
        companies={[makeCompany()]}
        selectedDealId="deal-1"
        onSelectDeal={() => {}}
        notes={[]}
        noteBody=""
        setNoteBody={() => {}}
        onAddNote={async () => {}}
        onCreateDeal={async () => {}}
        onMoveDeal={async () => {}}
        onArchiveDeal={async () => {}}
        followupSuggestion={{ editable_text: draft }}
      />
    );

    const drawer = screen.getByTestId("deal-drawer");
    expect(within(drawer).getByText(/sugestão do agente/i)).toBeInTheDocument();
    expect(within(drawer).getByText(draft)).toBeInTheDocument();

    await user.click(within(drawer).getByRole("button", { name: /^usar$/i }));

    const modal = await screen.findByRole("dialog", {
      name: /enviar follow-up/i,
    });
    expect(within(modal).getByLabelText(/rascunho/i)).toHaveValue(draft);
  });
});

function renderNovoDealForm(
  overrides: Partial<Parameters<typeof FunilPanel>[0]> = {}
) {
  const onCreateDeal = vi.fn();
  render(
    <FunilPanel
      deals={[]}
      stages={[...FUNIL_STAGES]}
      contacts={[makeContact()]}
      companies={[makeCompany()]}
      selectedDealId={null}
      onSelectDeal={() => {}}
      notes={[]}
      noteBody=""
      setNoteBody={() => {}}
      onAddNote={async () => {}}
      onCreateDeal={onCreateDeal}
      onMoveDeal={async () => {}}
      onArchiveDeal={async () => {}}
      {...overrides}
    />
  );
  return { onCreateDeal };
}

describe("FunilPanel Novo Lead form", () => {
  it("unit-1: Novo Lead form exposes name, contact fields, stage and value", async () => {
    const user = userEvent.setup();
    renderNovoDealForm();

    expect(
      screen.queryByRole("dialog", { name: /novo lead/i })
    ).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /^adicionar$/i }));

    const dialog = await screen.findByRole("dialog", { name: /novo lead/i });
    const form = within(dialog).getByRole("form", {
      name: /formulário de criação de lead/i,
    });
    expect(within(form).getByLabelText(/^nome/i)).toBeInTheDocument();
    expect(within(form).getByLabelText(/^e-mail$/i)).toBeInTheDocument();
    expect(within(form).getByLabelText(/^telefone$/i)).toBeInTheDocument();
    expect(within(form).getByLabelText(/^descrição$/i)).toBeInTheDocument();
    expect(within(form).getByLabelText(/^cidade$/i)).toBeInTheDocument();
    expect(within(form).getByLabelText(/^uf$/i)).toBeInTheDocument();
    expect(within(form).getByLabelText(/^tags$/i)).toBeInTheDocument();
    expect(within(form).getByLabelText(/^contato$/i)).toBeInTheDocument();
    expect(within(form).getByLabelText(/^empresa$/i)).toBeInTheDocument();
    expect(within(form).getByLabelText(/^estágio/i)).toBeInTheDocument();
    expect(within(form).getByLabelText(/^valor$/i)).toBeInTheDocument();
    expect(within(form).queryByLabelText(/^título/i)).not.toBeInTheDocument();
    expect(within(form).queryByLabelText(/^moeda$/i)).not.toBeInTheDocument();
    expect(within(form).queryByLabelText(/^status$/i)).not.toBeInTheDocument();

    await user.click(within(dialog).getByRole("button", { name: /^cancelar$/i }));
    expect(
      screen.queryByRole("dialog", { name: /novo lead/i })
    ).not.toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: /visualização lista/i }));
    await user.click(screen.getByRole("button", { name: /^adicionar$/i }));
    expect(
      await screen.findByRole("dialog", { name: /novo lead/i })
    ).toBeInTheDocument();
  });

  it("unit-2: submit with name and email sends contact payload and defaults to lead", async () => {
    const user = userEvent.setup();
    const { onCreateDeal } = renderNovoDealForm();

    await user.click(screen.getByRole("button", { name: /^adicionar$/i }));
    await user.type(screen.getByLabelText(/^nome/i), "Acme deal");
    await user.type(screen.getByLabelText(/^e-mail$/i), "ana@x.com");
    await user.click(screen.getByRole("button", { name: /^criar$/i }));

    expect(onCreateDeal).toHaveBeenCalledTimes(1);
    expect(onCreateDeal).toHaveBeenCalledWith(
      expect.objectContaining({
        title: "Acme deal",
        stage: "lead",
        contactId: null,
        referredByContactId: null,
        contact: expect.objectContaining({
          name: "Acme deal",
          email: "ana@x.com",
        }),
      })
    );
    expect(screen.queryByRole("tab", { name: /^contatos$/i })).not.toBeInTheDocument();
  });

  it("unit-3: submit with only name and no email/phone is deal-only", async () => {
    const user = userEvent.setup();
    const { onCreateDeal } = renderNovoDealForm();

    await user.click(screen.getByRole("button", { name: /^adicionar$/i }));
    await user.type(screen.getByLabelText(/^nome/i), "Só nome");
    await user.click(screen.getByRole("button", { name: /^criar$/i }));

    expect(onCreateDeal).toHaveBeenCalledTimes(1);
    const payload = onCreateDeal.mock.calls[0][0];
    expect(payload).toEqual(
      expect.objectContaining({
        title: "Só nome",
        stage: "lead",
        contactId: null,
        referredByContactId: null,
      })
    );
    expect(payload.contact).toBeUndefined();
  });

  it("unit-4: existing company select plus email sends companyId and contact fields", async () => {
    const user = userEvent.setup();
    const { onCreateDeal } = renderNovoDealForm();

    await user.click(screen.getByRole("button", { name: /^adicionar$/i }));
    expect(
      screen.queryByLabelText(/nome da empresa/i)
    ).not.toBeInTheDocument();

    await user.type(screen.getByLabelText(/^nome/i), "Deal com empresa");
    await user.type(screen.getByLabelText(/^e-mail$/i), "ana@x.com");
    await user.click(screen.getByRole("combobox", { name: /^empresa$/i }));
    await user.click(await screen.findByRole("option", { name: /^acme$/i }));
    await user.click(screen.getByRole("button", { name: /^criar$/i }));

    expect(onCreateDeal).toHaveBeenCalledTimes(1);
    expect(onCreateDeal).toHaveBeenCalledWith(
      expect.objectContaining({
        title: "Deal com empresa",
        companyId: "company-1",
        contact: expect.objectContaining({ email: "ana@x.com" }),
      })
    );
  });

  it("unit-5: description and referring contact go in the payload", async () => {
    const user = userEvent.setup();
    const { onCreateDeal } = renderNovoDealForm();

    await user.click(screen.getByRole("button", { name: /^adicionar$/i }));
    await user.type(screen.getByLabelText(/^nome/i), "Lead indicado");
    await user.type(
      screen.getByLabelText(/^descrição$/i),
      "Falamos no WhatsApp ontem"
    );
    await user.click(screen.getByRole("combobox", { name: /^contato$/i }));
    await user.click(await screen.findByRole("option", { name: /^joão$/i }));
    await user.click(screen.getByRole("button", { name: /^criar$/i }));

    expect(onCreateDeal).toHaveBeenCalledWith(
      expect.objectContaining({
        title: "Lead indicado",
        description: "Falamos no WhatsApp ontem",
        referredByContactId: "contact-1",
        contactId: null,
      })
    );
  });

  it("unit-6: clicking a card opens the drawer with the same fields for editing", async () => {
    const user = userEvent.setup();
    const onUpdateDeal = vi.fn();
    render(
      <FunilWithSelection
        deals={[
          makeDeal({
            id: "deal-1",
            title: "Acme Proposal",
            stage: "proposal",
          }),
        ]}
        stages={[...FUNIL_STAGES]}
        contacts={[makeContact()]}
        companies={[makeCompany()]}
        notes={[]}
        noteBody=""
        setNoteBody={() => {}}
        onAddNote={async () => {}}
        onCreateDeal={async () => {}}
        onUpdateDeal={onUpdateDeal}
        onMoveDeal={async () => {}}
        onArchiveDeal={async () => {}}
      />
    );

    await user.click(screen.getByRole("button", { name: /acme proposal/i }));
    const drawer = screen.getByTestId("deal-drawer");
    const form = within(drawer).getByRole("form", {
      name: /formulário de edição de lead/i,
    });
    expect(within(form).getByLabelText(/^nome/i)).toHaveValue("Acme Proposal");
    expect(within(form).getByLabelText(/^e-mail$/i)).toBeInTheDocument();
    expect(within(form).getByLabelText(/^telefone$/i)).toBeInTheDocument();
    expect(within(form).queryByLabelText(/^descrição$/i)).not.toBeInTheDocument();
    expect(within(drawer).getByRole("list", { name: /timeline/i })).toBeInTheDocument();

    await user.clear(within(form).getByLabelText(/^nome/i));
    await user.type(within(form).getByLabelText(/^nome/i), "Acme novo");
    await user.click(within(form).getByRole("button", { name: /^salvar$/i }));
    expect(onUpdateDeal).toHaveBeenCalledWith(
      expect.objectContaining({ title: "Acme novo" })
    );
  });
});

const DEAL_STAGE_DISPLAY: ReadonlyArray<readonly [string, string]> = [
  ["lead", "Lead"],
  ["qualified", "Qualificado"],
  ["proposal", "Proposta"],
  ["negotiation", "Negociação"],
  ["won", "Ganho"],
  ["lost", "Perdido"],
];

describe("FunilPanel stage labels (saas-empresario-br-task-crm-ui-2 unit-1 / REQ-007)", () => {
  it("kanban column titles and aria-labels use pt-BR DEAL_STAGE_LABELS, not the raw enum", () => {
    render(
      <FunilPanel
        deals={[makeDeal({ id: "deal-1", title: "Acme", stage: "lead" })]}
        stages={[...FUNIL_STAGES]}
        contacts={[makeContact()]}
        companies={[makeCompany()]}
        selectedDealId={null}
        onSelectDeal={() => {}}
        notes={[]}
        noteBody=""
        setNoteBody={() => {}}
        onAddNote={async () => {}}
        onCreateDeal={async () => {}}
        onMoveDeal={async () => {}}
        onArchiveDeal={async () => {}}
      />
    );

    for (const [canonical, label] of DEAL_STAGE_DISPLAY) {
      const heading = screen.getByRole("heading", { name: new RegExp(`^${label}$`) });
      expect(heading).toHaveTextContent(label);
      expect(heading.textContent).not.toBe(canonical);

      const column = screen.getByRole("group", { name: `Coluna ${label}` });
      expect(column).toHaveAttribute("aria-label", `Coluna ${label}`);
    }

    const leadColumn = screen.getByRole("group", { name: /coluna lead/i });
    expect(leadColumn).toHaveAttribute("aria-label", "Coluna Lead");
    expect(leadColumn).not.toHaveAttribute("aria-label", "Coluna lead");
  });

  it("unknown stage falls back to the raw value in the kanban heading and aria-label", () => {
    render(
      <FunilPanel
        deals={[]}
        stages={["custom-stage"]}
        contacts={[]}
        companies={[]}
        selectedDealId={null}
        onSelectDeal={() => {}}
        notes={[]}
        noteBody=""
        setNoteBody={() => {}}
        onAddNote={async () => {}}
        onCreateDeal={async () => {}}
        onMoveDeal={async () => {}}
        onArchiveDeal={async () => {}}
      />
    );

    expect(screen.getByRole("heading", { name: /^custom-stage$/ })).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Coluna custom-stage" })).toHaveAttribute(
      "aria-label",
      "Coluna custom-stage"
    );
  });

  it("lista Estágio column and drawer select show the lookup, not the raw enum", async () => {
    const user = userEvent.setup();
    render(
      <FunilPanel
        deals={[
          makeDeal({
            id: "deal-1",
            title: "Acme Proposal",
            stage: "proposal",
          }),
        ]}
        stages={[...FUNIL_STAGES]}
        contacts={[makeContact()]}
        companies={[makeCompany()]}
        selectedDealId="deal-1"
        onSelectDeal={() => {}}
        notes={[]}
        noteBody=""
        setNoteBody={() => {}}
        onAddNote={async () => {}}
        onCreateDeal={async () => {}}
        onMoveDeal={async () => {}}
        onArchiveDeal={async () => {}}
      />
    );

    const drawer = screen.getByTestId("deal-drawer");
    await user.click(within(drawer).getByRole("combobox", { name: /mover para/i }));
    expect(await screen.findByRole("option", { name: /^Negociação$/ })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: /^negotiation$/ })).not.toBeInTheDocument();
    await user.keyboard("{Escape}");

    fireEvent.click(screen.getByRole("tab", { name: /visualização lista/i }));
    const dataRow = screen.getAllByRole("row")[1];
    expect(dataRow).toHaveTextContent("Proposta");
    expect(dataRow).not.toHaveTextContent("proposal");
  });
});

function visibleText(value: string | null | undefined): string {
  return (value ?? "").replace(/\u00a0/g, " ");
}

describe("FunilPanel deal value (saas-empresario-br-task-crm-ui-2 unit-2 / REQ-007)", () => {
  it("kanban card and lista show R$ 1.500,00 not BRL 1500", () => {
    render(
      <FunilPanel
        deals={[
          makeDeal({
            id: "deal-1",
            title: "Acme Co",
            stage: "proposal",
            value: 1500,
            currency: "BRL",
          }),
        ]}
        stages={[...FUNIL_STAGES]}
        contacts={[makeContact()]}
        companies={[makeCompany()]}
        selectedDealId={null}
        onSelectDeal={() => {}}
        notes={[]}
        noteBody=""
        setNoteBody={() => {}}
        onAddNote={async () => {}}
        onCreateDeal={async () => {}}
        onMoveDeal={async () => {}}
        onArchiveDeal={async () => {}}
      />
    );

    const card = screen.getByRole("button", { name: /acme co/i });
    expect(visibleText(card.textContent)).toMatch(/R\$ 1\.500,00/);
    expect(card).not.toHaveTextContent("BRL");
    expect(card).not.toHaveTextContent("BRL 1500");

    fireEvent.click(screen.getByRole("tab", { name: /visualização lista/i }));
    const dataRow = screen.getAllByRole("row")[1];
    expect(visibleText(dataRow.textContent)).toMatch(/R\$ 1\.500,00/);
    expect(dataRow).not.toHaveTextContent("BRL 1500");
  });

  it("kanban card without value does not render BRL or undefined", () => {
    render(
      <FunilPanel
        deals={[
          makeDeal({
            id: "deal-empty",
            title: "Sem valor",
            stage: "lead",
            value: null,
            currency: null,
          }),
        ]}
        stages={[...FUNIL_STAGES]}
        contacts={[]}
        companies={[]}
        selectedDealId={null}
        onSelectDeal={() => {}}
        notes={[]}
        noteBody=""
        setNoteBody={() => {}}
        onAddNote={async () => {}}
        onCreateDeal={async () => {}}
        onMoveDeal={async () => {}}
        onArchiveDeal={async () => {}}
      />
    );

    const card = screen.getByRole("button", { name: /sem valor/i });
    expect(card.textContent).not.toMatch(/BRL/);
    expect(card.textContent).not.toMatch(/undefined/);
    expect(visibleText(card.textContent)).not.toMatch(/R\$/);
  });
});

describe("FunilPanel move persists canonical stage (saas-empresario-br-task-crm-ui-2 unit-3 / REQ-007)", () => {
  it("dropping onto Coluna Negociação calls onMoveDeal with negotiation, not the translated label", () => {
    const onMoveDeal = vi.fn(async () => {});

    render(
      <FunilPanel
        deals={[
          makeDeal({
            id: "deal-1",
            title: "Acme Proposal",
            stage: "proposal",
          }),
        ]}
        stages={[...FUNIL_STAGES]}
        contacts={[makeContact()]}
        companies={[makeCompany()]}
        selectedDealId={null}
        onSelectDeal={() => {}}
        notes={[]}
        noteBody=""
        setNoteBody={() => {}}
        onAddNote={async () => {}}
        onCreateDeal={async () => {}}
        onMoveDeal={onMoveDeal}
        onArchiveDeal={async () => {}}
      />
    );

    const column = screen.getByRole("group", { name: "Coluna Negociação" });
    expect(column).toHaveAttribute("aria-label", "Coluna Negociação");

    const card = screen.getByRole("button", { name: /acme proposal/i });
    const dataTransfer = makeDataTransfer();
    fireEvent.dragStart(card, { dataTransfer });
    fireEvent.drop(column, { dataTransfer });

    expect(onMoveDeal).toHaveBeenCalledWith("deal-1", "negotiation");
    expect(onMoveDeal).not.toHaveBeenCalledWith("deal-1", "Negociação");
  });

  it("drawer option Negociação still moves with canonical negotiation", async () => {
    const user = userEvent.setup();
    const onMoveDeal = vi.fn(async () => {});

    render(
      <FunilPanel
        deals={[
          makeDeal({
            id: "deal-1",
            title: "Acme Proposal",
            stage: "proposal",
          }),
        ]}
        stages={[...FUNIL_STAGES]}
        contacts={[makeContact()]}
        companies={[makeCompany()]}
        selectedDealId="deal-1"
        onSelectDeal={() => {}}
        notes={[]}
        noteBody=""
        setNoteBody={() => {}}
        onAddNote={async () => {}}
        onCreateDeal={async () => {}}
        onMoveDeal={onMoveDeal}
        onArchiveDeal={async () => {}}
      />
    );

    const drawer = screen.getByTestId("deal-drawer");
    await user.click(within(drawer).getByRole("combobox", { name: /mover para/i }));
    await user.click(await screen.findByRole("option", { name: /^Negociação$/ }));

    expect(onMoveDeal).toHaveBeenCalledWith("deal-1", "negotiation");
    expect(onMoveDeal).not.toHaveBeenCalledWith("deal-1", "Negociação");
  });
});
