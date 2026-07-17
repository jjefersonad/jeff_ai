# Jeff AI

**Jeff AI** is a general-purpose, self-hosted AI assistant running on your own model (Ollama) — a Claude that you own, that you use for *everything*, and that keeps improving itself.

## What Jeff AI is

Seven capabilities define the product:

1. **The same functions as Claude Code** — write and edit code, run tests, use git.
2. **Serve any task** — marketing campaigns, research, coding. There is no fixed list of use cases.
3. **Create and install skills** dynamically.
4. **Configure MCP servers** — the user connects whatever tools they want.
5. **Plan and execute.**
6. **Its own persistent memory**, of everything, in a database.
7. **Read its own source code** to keep improving.

Already implemented today: dynamic skills, persistent memory (read/write via `save_memory`/`search_memory`), image generation (with mandatory user approval), native Office document generation (`.docx`/`.xlsx`/`.pptx`), and self-extension (the agent creates its own tools and skills). **The MCP client does not exist yet** — connecting external MCP servers isn't possible yet.

For the full picture — the table of five primitives behind these capabilities, the graph architecture, approval tiers, and the list of known technical debt ("Known Debt") — see [CLAUDE.md](CLAUDE.md).

## How to run it

### Backend (Python/LangGraph)

```bash
cd backend
pip install -e ".[dev]"          # install dependencies
docker compose up -d jeff_ia_postgres jeff_ia_redis   # Postgres + Redis
make dev                         # checks Postgres, then runs `langgraph dev`
```

### Frontend (Next.js 16 + React 19)

```bash
cd frontend
yarn install
yarn dev
```

### Docker (full stack)

```bash
docker compose up -d                                # Postgres + pgvector + other services
docker compose --profile admin up -d                # + pgAdmin
docker-compose -f docker-compose.ollama.yml up -d    # with local Ollama
docker-compose logs -f
```

### Ports

| Service | Port |
|---|---|
| Frontend | 3000 |
| Backend | 8000 |
| Media/file server | 8080 |
| pgAdmin | 5050 |

## How to configure it

Environment variables in `backend/.env`:

**Required**

| Variable | Description | Default |
|---|---|---|
| `POSTGRES_URI` | PostgreSQL connection string | — |
| `OLLAMA_BASE_URL` | Ollama server endpoint | `http://10.0.0.214:11434` |
| `OLLAMA_MODEL` | Ollama model name | `minimax-m2.7:cloud` |
| `ADMIN_USERNAME` | Username for the first admin user, created once on startup if the `users` table is empty | `admin` |
| `ADMIN_PASSWORD_HASH` | Bcrypt hash for that admin's password (never the plain password) | — |

### Default login

On first startup with an empty `users` table, the backend bootstraps one admin account from `ADMIN_USERNAME`/`ADMIN_PASSWORD_HASH`. The local dev database currently ships with:

- **Username:** `admin`
- **Password:** `admin123!`

This is a **dev-only default** — change it before any real deployment. Since the bootstrap only runs once (it's a no-op once `users` has any row), rotating the password afterwards means generating a new bcrypt hash (`security.get_password_hash`) and running `UPDATE users SET password_hash = ...` directly in Postgres — updating `.env` alone has no effect on an existing row.

**Optional**

| Variable | Effect |
|---|---|
| `TAVILY_API_KEY` | Enables web search |
| `GOOGLE_API_KEY` | Enables image generation via Gemini |
| `LANGSMITH_API_KEY` | Enables LangSmith tracing |
| `JEFF_AI_TZ` | IANA timezone (e.g. `America/Sao_Paulo`) used to fill in the local date in the system prompt; defaults to `UTC` |

## Share the project

Want to promote Jeff AI on LinkedIn or Instagram? See the [promotion guide](docs/SOCIAL_MEDIA_GUIDE.md), with tone of voice, ready-to-use templates, and asset recommendations per platform.

## Resources

- [CLAUDE.md](CLAUDE.md) — architecture, exact commands, and known technical debt
- [Project architecture](docs/ARCHITECTURE.md)
- [LangGraph documentation](https://langchain-ai.github.io/langgraph/)
- [DeepAgents](https://github.com/langchain-ai/deepagents)
- [Ollama documentation](https://ollama.com/)
