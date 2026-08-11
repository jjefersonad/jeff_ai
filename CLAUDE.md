# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Jeff AI** is a general-purpose, self-hosted AI assistant running on the user's own model (Ollama) — a Claude that you own, that you use for *everything*, and that improves itself.

The seven capabilities that define it:

1. **The same functions as Claude Code** — write and edit code, run tests, use git.
2. **Serve any task** — marketing campaigns, research, coding. There is no fixed list of use cases.
3. **Create and install skills** dynamically.
4. **Configure MCP servers** — the user plugs in whatever tools they want.
5. **Plan and execute.**
6. **Its own persistent memory** in the database, of everything.
7. **Read its own source code** to improve continuously.

### The architectural principle that follows from this

> **Because it serves *everything*, a new capability arrives as a SKILL or an MCP server — never as a mode or a subagent.**

You cannot enumerate modes for an unbounded set of use cases. A mode or subagent per use case costs O(n) in code, prompt and routing; a skill costs O(1) — you drop a markdown file in `backend/skills/`. Marketing already proves the pattern: `backend/skills/{brand-guidelines,canvas-design,marketing-image-generation}` deliver the capability with zero subagents.

**When you are tempted to add a subagent, add a skill instead. When you are tempted to add a mode, ask what problem it solves that a skill does not.**

### What Jeff AI is NOT

- **Not a requirements-document generator.** Earlier versions of this file said so; it was wrong. Requirements docs are one skill among many.
- **Not an SDD engine.** Spec-driven development is a *skill* of the product, built on `src/tools/sdd_tools.py`.
- **Not related to OpenSddRag.** OpenSddRag is the *development* tooling used to build Jeff AI (see the section at the bottom). It is a separate project and a separate product. **Never wire the Jeff AI agent to it.**

---

## The five primitives

Everything Jeff AI does comes out of these. Marketing, research, coding and self-improvement need no domain-specific machinery beyond them.

| # | Primitive | Where it lives | Status |
|---|-----------|----------------|--------|
| 1 | Agent loop (ReAct) | `deepagents.create_deep_agent` | ✅ works |
| 2 | Flat tool set | `src/tools/` | ✅ works (~35 tools) |
| 3 | Skills, loaded on demand | `backend/skills/` + `src/tools/self_extension.py` | ✅ works |
| 4 | **MCP client** | — | ❌ **does not exist** |
| 5 | Persistent memory | Postgres store + `src/tools/memory_tools.py` | ✅ works (see Known Debt #2 for the nuance) |

---

## Commands

### Backend (Python/LangGraph)
```bash
cd backend

pip install -e ".[dev]"   # install dependencies
ruff check .              # lint
mypy .                    # type check
pytest                    # tests
make dev                  # checks Postgres is reachable, then runs `langgraph dev`
python main.py            # interactive chat with the agent
```

`make dev` requires Postgres (`docker compose up -d jeff_ia_postgres jeff_ia_redis`). Running bare `langgraph dev` without it fails after 30s with a raw `psycopg_pool.PoolTimeout`; `make dev` fails in ~5s with an actionable message instead.

### Frontend (Next.js 16 + React 19)
```bash
cd frontend

yarn install
yarn dev                  # dev server
yarn build                # production build
yarn lint / yarn lint:fix
yarn format
```

### Database & Docker

Official Compose layout (exactly three files):

| File | Role |
|------|------|
| `docker-compose.yml` | Daily dev (app + Postgres/Redis + telegram_gateway; pgAdmin via `--profile admin`) |
| `docker-compose.prod.yml` | Production app only (`frontend` + `backend`; infra/channels external) |
| `docker-compose.all.yml` | Full self-contained stack (app + DBs + Ollama + Evolution + telegram_gateway) |

```bash
docker compose up -d                            # daily dev
docker compose --profile admin up -d            # + pgAdmin (:5050)
docker compose -f docker-compose.prod.yml up -d # prod: frontend + backend only
docker compose -f docker-compose.all.yml up -d  # full stack (Ollama + Evolution + gateway)
docker compose logs -f
docker compose down
```

**Ports (dev/`all` host maps):** frontend 3002 · backend 8001 · pgAdmin 5050 · Evolution API 8085 · Ollama 11434

---

## Architecture

### Graphs

`backend/langgraph.json` exposes four graph IDs, but they are **one graph**:

- **`unified`** — the real graph (`src/agents/unified/agent.py`). Built via `create_deep_agent` with the full flat tool set, the subagents, and a tier-based `interrupt_on`.
- **`agent`, `sdd_agent`, `assistant`** — backward-compat shims in `src/composition/graphs.py`. They wrap the same compiled `unified` object. See Known Debt: they do **not** currently change behaviour.

### Backend layout

- `src/agents/unified/agent.py` — the graph. Tool registry, subagent registry, prompts, backend routes.
- `src/agents/unified/tier_config.py` — declarative approval tiers (see below).
- `src/tools/` — the flat tool set: file ops, code editing, git, tests, web search (Tavily), scientific search, image generation, Office documents, memory, self-extension, SDD scaffolding.
- `src/models/` — Ollama/Gemini model config + Pydantic schemas for tool inputs.
- `backend/skills/` — skills loaded live by deepagents from the `/skills/` route.
- `backend/outputs/` — generated artifacts (documents, images, `.specify/` SDD scaffolding).

### Approval tiers (`tier_config.py`)

The safety model. `build_interrupt_on()` turns the declarative registry into the `interrupt_on` dict passed to `create_deep_agent`. Only Tier 3+ gates the graph.

| Tier | Behaviour | Tools |
|------|-----------|-------|
| 1 | Auto — runs immediately | reads, greps, `run_tests`, `git_status`, `git_diff`, searches |
| 2 | Runs immediately, frontend notifies | new-file writes, Office docs, `save_memory`, `merge_generated_files` |
| 3 | **Interrupt** — pauses with diff preview, `approve`/`edit`/`reject` | `edit_file`, `patch_file`, `multi_file_edit`, `git_commit` |
| 4 | **Denylist + interrupt** | `run_shell_command` |

**Never bypass `interrupt_on`.** It is the only thing standing between the agent and the user's real repository.

### Image generation

Image requests go to `image_design_subagent`, which presents a design plan and then calls `create_image_from_prompt` immediately (no HITL `interrupt_on` on image generation). The image is generated via Gemini and saved to `backend/outputs/images/`; the style is stored per-thread via `save_design_style` after a successful generation. The tool returns `{path, url, metadata}` — **always use `url` in markdown, never `path`.**

### Office documents / PDF

`create_docx_document`, `create_xlsx_spreadsheet`, `create_pptx_presentation`, `create_pdf_document` — canonical path is the HTML pipeline (`RenderHtmlDocument` + converters; PDF via WeasyPrint). Prefer `preview_html_document` for styled docs, then finalize (optionally `from_preview`). No subagent, no approval gate. Each returns `{path, url, metadata}` — **always use `url`**. Files land in `backend/outputs/documents/{kind}/` and are served by the backend's own `http.app` (`src/infrastructure/web/webapp.py`, mounted via the `LANGGRAPH_HTTP` env var — see `docker-compose.yml`) at `GET /api/files/{kind}/{name}` (restricted to `kind ∈ {docx,xlsx,pptx,pdf,html}`; rejects traversal with 400, missing files with 404). **`image_server.py:8080` no longer serves this route** (migrated in `consolidate-http-routes-langgraph`) — reach it via the frontend origin (`http://localhost:3000`, rewritten server-side per `next.config.ts`) or the backend's docker-exposed port directly.

**Creation only** — editing existing Office/PDF files is out of scope. The skills in `backend/skills/{docx,xlsx,pptx,pdf}/SKILL.md` point at these tools; anything under `scripts/office/*` is marked `⚠️ LEGADO` and kept only for reference.

### Persistence

- **Checkpointer** — Postgres via `POSTGRES_URI` (conversation history).
- **Store** — Postgres, long-term memory at `/memories/` (currently disabled, see Known Debt).
- **Filesystem** — per-thread routes for `/workspace/` and `/outputs/`; shared routes for `/repo/`, `/specify/`, `/skills/`.

---

## Known Debt — read this before trusting the code

The `unified-dev-agent` change was archived as complete while parts of it were not built. **Docstrings in `src/agents/unified/agent.py` describe behaviour the code does not have.** Verify before you rely on any of it.

1. **The mode system is a facade.** `classify_mode()` has zero call sites. `mode_detector` exists only in comments. Nothing reads `configurable["mode"]`. `with_mode()` does not rebuild the graph — it only attaches config, and its `"recurable"` key is a typo for `recursion_limit`. **Consequence: `agent`, `sdd_agent` and `assistant` all run the `chat` prompt.** `_PROMPT_SDD` and `_PROMPT_REQUIREMENTS` are dead strings. The frontend `ModeSelector` sends a mode the backend ignores.
2. **Memory: two paths, don't confuse them.** `save_memory` / `search_memory` use `get_store()` — the LangGraph store, injected by the runtime from `langgraph.json` (`store: postgres` + pgvector `index`). **They work, and always have** (verified: 5 items in the `("memories",)` namespace, 5 embeddings). Separately, the `/memories/` **filesystem** route (`StoreBackend` — lets the agent `ls`/`read_file` its memory) used to be gated on the non-existent mode system and was left unmounted; that is fixed. An earlier version of this file claimed "memory is off" — that was **wrong**.
3. **No tests on the dangerous tools.** `code_editing_tools.py`, `git_tools.py`, `test_runner_tools.py` and `tier_config.py` (~1,066 lines that edit source files, commit, and run shell) have **zero tests**.
4. **`.gitignore` swallows real source.** The unanchored `lib/` rule (line 15, a Python-venv idiom) ignores `frontend/src/lib/` and `frontend/src/app/lib/`. `utils.ts` (the `cn` helper, imported by 21 files), `config.ts` and `modes.ts` are **not in git**. The frontend does not build from a fresh clone.
5. **Dead legacy agents.** `src/agents/requirements_specialist.py`, `src/agents/assistant/agent.py` and `src/agents/sdd/orchestrator.py` are no longer imported by `graphs.py`, but still sit on disk with the original prompts. Do not edit them by mistake.
6. **The subagents should not exist.** The 7 SDD subagents (`src/agents/sdd/subagents/`) and `fullstack_subagent` reimplement in Python what belongs in a `SKILL.md`. They are slated for deletion — do not extend them.

---

## Environment Variables

**One file:** `./.env` at the repository root is the only active source of truth for operators
and for Compose. Copy the catalog with `cp .env.example .env`. Bare-metal
(`python main.py`, `make dev`, `pytest`) loads the same file via
`src/composition/env.py:load_env()` (root only — no dual-load of `backend/.env`).
Compose services use `env_file: .env` and `${VAR}` interpolation from the root.

`backend/.env.example` and `frontend/.env.example` are **stubs** that point at the root
template. If you still have a local `backend/.env`, migrate its keys into `./.env` and stop
using the per-project files.

**`BASE_URL`** is the public base URL of the **backend** (absolute URLs for documents/media and
server-to-server callers such as Evolution). It is **not** an alias for `DOCUMENT_BASE_URL`
(removed — **BREAKING**). Fallback when unset: `FRONTEND_ORIGIN`, then `http://localhost:3000`.
Keep these distinct from `NEXT_PUBLIC_API_URL` (browser-facing API origin) and
`FRONTEND_ORIGIN` (CORS / cookies).

Root `./.env` — infra/shared: `POSTGRES_URI`, `REDIS_PASSWORD` (dev) or `REDIS_URI` (prod),
`LANGSMITH_API_KEY`, `OLLAMA_BASE_URL`, `OLLAMA_MODEL`, `FRONTEND_ORIGIN`, `BASE_URL`.
Production (`docker-compose.prod.yml`): `POSTGRES_URI`/`REDIS_URI` must point at externally
managed instances (no local Postgres/Redis containers), plus `NEXT_PUBLIC_API_URL`. Secrets and
Python tuning also live in the root file: `GOOGLE_API_KEY`, `TAVILY_API_KEY`,
`OPENROUTER_API_KEY`, `ADMIN_USERNAME`/`ADMIN_PASSWORD_HASH`, `TELEGRAM_BOT_TOKEN`/
`TELEGRAM_AUTHORIZED_CHAT_ID`, `INTEGRATION_CREDENTIALS_KEY`, `OLLAMA_NUM_CTX`, `SESSION_TTL`,
`SHELL_COMMAND_TIMEOUT`, etc. Optional: `JEFF_AI_TZ`, `SKILLS_ALLOWLIST`,
`EVOLUTION_API_URL`/`EVOLUTION_API_KEY`/`EVOLUTION_INSTANCE_NAME`/`EVOLUTION_WEBHOOK_TOKEN`
(WhatsApp — without these four the channel does not authenticate). Dev-local /
`docker-compose.all.yml`: `POSTGRES_DB`/`POSTGRES_USER`/`POSTGRES_PASSWORD` (defaults
`jeff_ia`/`jeff_ia`/`jeff_ia`), `PGADMIN_DEFAULT_*`, and when using the Evolution bundle
`EVOLUTION_POSTGRES_PASSWORD`/`EVOLUTION_REDIS_PASSWORD`/`EVOLUTION_SERVER_URL`.
`EVOLUTION_WEBHOOK_TOKEN` is embedded in the webhook URL
(`/api/webhooks/whatsapp/<token>`) — the route's real auth, since that path is in
`PUBLIC_PATHS`.

**`TELEGRAM_BOT_USERNAME`** / **`WHATSAPP_BUSINESS_NUMBER`** (both optional): public
`@handle`/E.164 number used to build one-click deep links (`t.me/<username>?start=<code>`,
`wa.me/<number>?text=<code>`) on the "Adicionar integração" flow. Read at runtime by
`GET /api/integrations/channel-config` (`require_auth`) — deliberately **not**
`NEXT_PUBLIC_*`, so rotating either value (e.g. after a WhatsApp number ban) only needs a
backend restart, not a frontend rebuild. Missing either value just hides that channel's
deep link; the copy-code fallback keeps working.

See `./.env.example` for the full commented catalog.

### Production deploy

`docker-compose.prod.yml` is standalone and declares **only** `frontend` + `backend`. Fill in
`./.env` from `./.env.example`, then:

```bash
docker compose -f docker-compose.prod.yml up -d
```

This builds the frontend with `target: prod` (`next build && next start` — see
`frontend/Dockerfile.frontend`). Postgres/Redis/Ollama/Evolution/Telegram are **not** in this
file — point `POSTGRES_URI`/`REDIS_URI`/`OLLAMA_BASE_URL`/`EVOLUTION_*` at managed instances.
Compose fails fast if `POSTGRES_URI` or `REDIS_URI` is unset. For a self-contained stack
including `telegram_gateway` and Evolution, use `docker-compose.all.yml` instead.
Backend uses `env_file: .env` (root).

---

## OpenSddRag — development tooling only

> **OpenSddRag is a separate project and is NOT part of the Jeff AI product.** It is the spec-driven-development system *we use to build Jeff AI*. The specs, proposals and designs for this repository live in it. The Jeff AI agent never talks to it — do not add it as a runtime dependency, and do not confuse it with Jeff AI's own internal SDD feature (`src/agents/sdd/` + `src/tools/sdd_tools.py`).

- **MCP server:** `opensddrag` (http://localhost:8000), configured in `.mcp.json`
- **Project slug:** `jeff-ai`
- **Skills:** `.claude/skills/opensddrag-*/SKILL.md` · **Commands:** `.claude/commands/opsr/`

The server exposes these tools under the `opensddrag` namespace: `create_artifact`, `read_artifact`, `list_artifacts`, `update_artifact`, `validate_artifact`, `link_artifacts`, `get_relationships`, `search_semantic`, `recall_episodes`, `get_working_context`, `update_working_context`, `record_trace`.

> If those tools are not in your active tool list, the server is not connected. Start it with `docker compose up -d` and reload the project. Do not work around a missing server.

### Before implementing any feature

Search for existing specs first: `search_semantic(query="<topic>", project_slug="jeff-ai")`

### SDD commands

| Command | When to use |
|---------|-------------|
| `/opsr:propose` | Start here — capture intent and scope before any code |
| `/opsr:spec` | Formalize requirements (Purpose / SHALL / Scenarios) |
| `/opsr:design` | Document technical decisions and trade-offs |
| `/opsr:tasks` | Decompose a spec into atomic tasks (< 4h each) |
| `/opsr:apply` | Implement the next pending task against spec criteria |
| `/opsr:flow` | Run the full flow end-to-end for a feature |
| `/opsr:search` | Semantic search over specs and past work |
| `/opsr:status` | Show what is in progress and what is done |
| `/opsr:archive` | Mark a completed feature as archived |

```
/opsr:propose → /opsr:spec → /opsr:design → /opsr:tasks → /opsr:apply → /opsr:archive
```
<!-- opensddrag:start -->
---

## OpenSddRag — SDD + Harness

This project uses **OpenSddRag** for Spec-Driven Development with persistent semantic memory.

- **MCP server name:** `opensddrag` (http://localhost:8000) — configured in `.mcp.json`
- **Project slug:** `jeff-ai`
- **Skills:** `.claude/skills/opensddrag-*/SKILL.md`
- **Commands:** `.claude/commands/opsr/`

### MCP Tools (opensddrag server)

The `opensddrag` MCP server exposes these tools — they appear in your tool list under the `opensddrag` namespace:

| Tool | Purpose |
|------|---------|
| `create_artifact` | Create proposals, specs, designs, tasks |
| `read_artifact` | Read an artifact by name |
| `list_artifacts` | List artifacts with type/status filters |
| `update_artifact` | Update content or status |
| `validate_artifact` | Check spec structure |
| `link_artifacts` | Link artifacts (implements / depends_on / relates_to) |
| `get_relationships` | Get linked artifacts |
| `search_semantic` | Semantic search via pgvector |
| `recall_episodes` | Find past agent actions (episodic memory) |
| `get_working_context` | Get active session context |
| `update_working_context` | Update session context |
| `record_trace` | Log an action to episodic memory |

> If these tools are NOT in your active tool list, the server is not connected.
> Start it with `docker compose up -d` and reload the project. Do not attempt to work around a missing server.

### Before implementing any feature

Always search for existing specs first:

```
search_semantic(query="<topic>", project_slug="jeff-ai")
```

### SDD Commands

| Command | When to use |
|---------|-------------|
| `/opsr:propose` | Start here — capture intent and scope before any code |
| `/opsr:spec` | Formalize requirements (Purpose / SHALL / Scenarios) |
| `/opsr:design` | Document technical decisions and trade-offs |
| `/opsr:tasks` | Decompose spec into atomic tasks (< 4h each) |
| `/opsr:apply` | Implement the next pending task against spec criteria |
| `/opsr:flow` | Run the full flow end-to-end for a feature |
| `/opsr:search` | Semantic search over specs and past work |
| `/opsr:status` | Show what's in progress and what's done |
| `/opsr:archive` | Mark a completed feature as archived |

### SDD Flow

```
/opsr:propose → /opsr:spec → /opsr:design → /opsr:tasks → /opsr:apply → /opsr:archive
```
<!-- opensddrag:end -->
