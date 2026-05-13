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