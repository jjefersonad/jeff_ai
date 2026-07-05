# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Jeff AI** - A deep agent developer assistant that generates requirement documents using LangGraph orchestration. The system uses a main orchestrator agent that delegates tasks to subagents for creating structured requirement documents.

## Commands

### Backend (Python/LangGraph)
```bash
cd backend

# Install dependencies
pip install -e ".[dev]"

# Run linting
ruff check .

# Type checking
mypy .

# Run tests
pytest

# Start LangGraph API server
langgraph dev

# Chat with agent (interactive)
python main.py
```

### Frontend (Next.js)
```bash
cd frontend

# Install dependencies
yarn install

# Development server
yarn dev

# Build for production
yarn build

# Linting
yarn lint
yarn lint:fix

# Format code
yarn format
```

### Database
```bash
# Start PostgreSQL with pgvector
docker compose up -d

# Access pgAdmin (optional, on port 5050)
docker compose --profile admin up -d
```

### Docker (Development)
```bash
# Without local Ollama (use external Ollama server)
docker-compose up -d

# With local Ollama
docker-compose -f docker-compose.ollama.yml up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

**Ports exposed:**
- Frontend: 3000
- Backend: 8000
- pgAdmin: 5050 (use `--profile admin`)

## Architecture

### Backend Structure
- **main.py**: Entry point for interactive chat with the agent
- **src/agents/requirements_specialist.py**: Main orchestrator agent using `create_deep_agent` from deepagents
- **src/agents/subagents/fullstack.py**: SubAgent for creating requirement document sections
- **src/tools/**: Custom tools (file operations, web search via Tavily, spec tools)
- **src/models/**: LLM model configurations (Ollama, Gemini)
- **langgraph.json**: LangGraph API configuration with Postgres checkpointer/store

### Frontend Structure (Next.js 16 + React 19)
- **src/**: App components, API hooks using SWR and LangGraph SDK
- Uses **Radix UI** components and **Tailwind CSS** for styling
- Connects to LangGraph API via `@langchain/langgraph-sdk`

### Agent Flow
1. User submits a request
2. Orchestrator agent (requirements_specialist) decomposes into tasks using `write_todos`
3. Tasks delegated to `fullstack_subagent` via `task()` function
4. Results consolidated using `merge_generated_files` tool
5. Final document saved to `backend/outputs/`

### Persistence
- **Checkpointer**: Postgres via `POSTGRES_URI` (conversation history)
- **Store**: Postgres for long-term memory (`/memories/`)
- **Filesystem**: Outputs saved to `backend/outputs/`

### Key Configuration (langgraph.json)
- Checkpointer and store use environment variable `POSTGRES_URI`
- Ollama endpoint: `OLLAMA_BASE_URL` (default: `http://10.0.0.214:11434`)
- Model: `OLLAMA_MODEL` (default: `minimax-m2.7:cloud`)

## Environment Variables

Required in `backend/.env`:
- `POSTGRES_URI`: PostgreSQL connection string
- `OLLAMA_BASE_URL`: Ollama server endpoint
- `OLLAMA_MODEL`: Model name to use

Optional:
- `TAVILY_API_KEY`: Web search
- `GOOGLE_API_KEY`: Gemini model
- `LANGSMITH_API_KEY`: Tracing/debugging

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

