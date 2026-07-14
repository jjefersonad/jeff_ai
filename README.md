# Jeff AI

Jeff AI é um assistente de agente profundo (deep agent) para desenvolvedores, construído sobre **LangGraph** + **DeepAgents**. Ele expõe três grafos independentes: um orquestrador que gera documentos de requisitos delegando seções a subagentes, um pipeline de Spec-Driven Development de 7 fases, e um assistente de uso geral capaz de gerar imagens e documentos Office.

## Funcionalidades

- **Documentos de requisitos** — orquestrador decompõe o pedido em tarefas e delega ao `fullstack_subagent`, consolidando o resultado num arquivo único
- **Pipeline SDD** — 7 fases (constitution → specify → clarify → plan → analyze → tasks → implement), cada uma com seu subagente
- **Assistente geral** — busca web, execução de shell, descoberta/instalação de skills externas e geração de tools em runtime
- **Geração de imagens** — planejamento de design com **aprovação obrigatória do usuário** antes de gerar (via Gemini), com memória de estilo por thread
- **Documentos Office nativos** — `.docx`, `.xlsx` e `.pptx` gerados em Python puro (sem pandoc/LibreOffice/Node)
- **Persistência** — histórico e memória de longo prazo em PostgreSQL + pgvector
- **Múltiplos provedores de LLM** — Ollama, Gemini, OpenAI, OpenRouter, Anthropic

## Grafos

O `backend/langgraph.json` registra três grafos, todos expostos por `src.composition.graphs`:

| `graph_id` | Papel | Entrypoint |
|------------|-------|------------|
| `agent` | Orquestrador de documentos de requisitos | `src/agents/requirements_specialist.py` |
| `sdd_agent` | Pipeline Spec-Driven Development (7 fases) | `src/agents/sdd/orchestrator.py` |
| `assistant` | Assistente de propósito geral | `src/agents/assistant/agent.py` |

## Tech Stack

**Backend**
- Python 3.11+
- LangGraph (orquestração) + DeepAgents (implementação dos agentes)
- PostgreSQL 15 com pgvector (checkpointer, store e embeddings)
- Redis (fila/broker do LangGraph API)
- python-docx, openpyxl, python-pptx (geração Office)
- FastAPI + Uvicorn (servidor de mídia)

**Frontend**
- Next.js 16 · React 19
- Tailwind CSS · Radix UI
- `@langchain/langgraph-sdk`

## Quickstart

### Pré-requisitos

- Docker Compose
- Servidor Ollama acessível (local ou remoto)
- **`LANGSMITH_API_KEY`** — obrigatório para o LangGraph API subir

### 1. Obter a LangSmith API Key

1. Acesse [smith.langchain.com](https://smith.langchain.com)
2. Faça login ou crie uma conta
3. **Settings** → **API Keys** → **Create API Key**
4. Copie a chave gerada

### 2. Configurar variáveis de ambiente

```bash
cp backend/.env.example backend/.env
```

Edite `backend/.env` e preencha no mínimo:

```bash
LANGSMITH_API_KEY=lsv2_pt_sua_chave_aqui
OLLAMA_BASE_URL=http://10.0.0.214:11434
OLLAMA_MODEL=minimax-m2.7:cloud
```

**Nota:** se o Ollama roda na sua máquina, use `http://host.docker.internal:11434` a partir dos containers.

### 3. Subir a stack

```bash
# Ollama externo (padrão)
docker compose up -d

# Ou com Ollama local em container
docker compose -f docker-compose.ollama.yml up -d

# Logs
docker compose logs -f

# pgAdmin (opcional)
docker compose --profile admin up -d
```

Acesse [http://localhost:3000](http://localhost:3000).

### Portas expostas

| Serviço | Host | Container |
|---------|------|-----------|
| Frontend | `3000` | 3000 |
| Backend (LangGraph API) | `8001` | 8000 |
| Servidor de mídia | `8080` | 8080 |
| PostgreSQL | `5436` | 5432 |
| Redis | `6379` | 6379 |
| pgAdmin (profile `admin`) | `5050` | 80 |

### Interface web

Ao acessar [http://localhost:3000](http://localhost:3000), configure:

- **Deployment URL**: `http://localhost:8001` (stack Docker) ou `http://127.0.0.1:2024` (`langgraph dev` local)
- **Assistant ID**: `agent`, `sdd_agent` ou `assistant`

## Desenvolvimento local (sem Docker)

O banco continua vindo do Compose; só o backend e o frontend rodam na máquina.

```bash
docker compose up -d jeff_ia_postgres jeff_ia_redis
```

**Backend** (LangGraph API em `http://127.0.0.1:2024`):

```bash
cd backend
pip install -e ".[dev]"
make dev
```

`make dev` valida que o Postgres está acessível antes de subir `langgraph dev` e falha rápido com instrução clara se não estiver (em vez do timeout de 30s do `psycopg_pool`).

**Frontend**:

```bash
cd frontend
yarn install
yarn dev
```

## Configuração

### Variáveis de ambiente (`backend/.env`)

| Variável | Descrição | Exemplo |
|----------|-----------|---------|
| `LANGSMITH_API_KEY` | **Obrigatório** — sem ela o LangGraph API não sobe | `lsv2_pt_...` |
| `POSTGRES_URI` | Conexão PostgreSQL | `postgresql://jeff_ia:jeff_ia@localhost:5436/jeff_ia` |
| `OLLAMA_BASE_URL` | Endpoint do servidor Ollama | `http://localhost:11434` |
| `OLLAMA_MODEL` | Modelo Ollama padrão | `minimax-m2.7:cloud` |
| `GOOGLE_API_KEY` | Gemini — **necessário para gerar imagens** | `AIza...` |
| `TAVILY_API_KEY` | Busca web | `tvly-...` |
| `SKILLS_ALLOWLIST` | Repos de terceiros liberados para instalar skills | `usenotra/skills` |

Opcionais: `OPENAI_API_KEY`, `OPENROUTER_API_KEY`, `LANGCHAIN_TRACING_V2`, `LANGSMITH_PROJECT`.

## Arquitetura

O backend segue **Clean Architecture / DDD**, com a Regra da Dependência apontando para dentro e verificada automaticamente por `import-linter`.

```
┌──────────────────────────────────────────────────────────────┐
│                     Frontend (Next.js)                       │
│                   http://localhost:3000                      │
└──────────────────────────────────────────────────────────────┘
             │                                  │
             ▼                                  ▼
┌───────────────────────────┐   ┌──────────────────────────────┐
│    LangGraph API :8001    │   │  Servidor de mídia :8080     │
│  agent · sdd_agent ·      │   │  imagens · referências ·     │
│  assistant                │   │  documentos Office           │
└───────────────────────────┘   └──────────────────────────────┘
             │                                  │
             ▼                                  ▼
┌───────────────────────────┐   ┌──────────────────────────────┐
│  PostgreSQL + pgvector    │   │  backend/outputs/            │
│  checkpointer · store     │   │  (filesystem compartilhado)  │
└───────────────────────────┘   └──────────────────────────────┘
```

### Camadas

```
composition  →  infrastructure  →  application  →  domain
```

- **`domain/`** — regras de negócio puras (documentos, imaging, requirements, SDD). Sem frameworks, sem I/O.
- **`application/`** — casos de uso e *ports* (interfaces): `image_gen`, `document_writer`, `style_repository`, …
- **`infrastructure/`** — adapters concretos: Gemini, python-docx/openpyxl/python-pptx, filesystem, Postgres store.
- **`composition/`** — injeção de dependências e exposição dos grafos (`graphs.py`).

O núcleo (`domain` + `application`) é proibido de importar `langgraph`, `deepagents`, `langchain` ou drivers de banco — o contrato está em `pyproject.toml` e é executado por `make arch`.

### Estrutura de diretórios

```
jeff_ai/
├── backend/
│   ├── src/
│   │   ├── agents/           # Grafos e subagentes
│   │   │   ├── requirements_specialist.py
│   │   │   ├── assistant/
│   │   │   ├── sdd/          # Pipeline SDD (7 fases)
│   │   │   └── subagents/    # fullstack, image_design
│   │   ├── domain/           # Regras de negócio puras
│   │   ├── application/      # Casos de uso + ports
│   │   ├── infrastructure/   # Adapters (Gemini, Office, FS, Postgres)
│   │   ├── composition/      # DI + registro dos grafos
│   │   ├── models/           # Configs de LLM + schemas Pydantic
│   │   └── tools/            # Ferramentas dos agentes
│   ├── skills/               # Skills do DeepAgent (docx, pptx, xlsx, design…)
│   ├── outputs/              # Artefatos gerados (docs, imagens)
│   ├── image_server.py       # FastAPI que serve mídia na :8080
│   └── langgraph.json
├── frontend/
├── docs/ARCHITECTURE.md      # Documento de arquitetura (baseline)
└── docker-compose.yml
```

## Fluxos

### Documento de requisitos (`agent`)

1. O orquestrador cria as tarefas com `write_todos` (uma por seção)
2. Delega cada seção ao `fullstack_subagent` via `task()`
3. Consolida tudo com `merge_generated_files`
4. Salva o documento final em `backend/outputs/{thread_id}/`

O documento cobre visão geral, requisitos funcionais e não funcionais, casos de uso, modelagem de dados, interface e considerações de segurança.

### Geração de imagens

1. Pedidos de imagem/banner/design são delegados ao `image_design_subagent`
2. O subagente analisa o contexto e apresenta um **plano de design**
3. O grafo **pausa** (`interrupt_on`) e exige aprovação explícita — `approve`, `edit` ou `reject`. Nenhuma imagem é gerada sem isso.
4. Aprovado, a imagem é gerada via Gemini e salva em `backend/outputs/images/`; o estilo aprovado fica na memória da thread para reuso ("na mesma vibe")

### Documentos Office

Gerados **diretamente pelo agente**, sem subagente nem aprovação:

| Tool | Formato | Biblioteca |
|------|---------|------------|
| `create_docx_document` | `.docx` | python-docx |
| `create_xlsx_spreadsheet` | `.xlsx` | openpyxl |
| `create_pptx_presentation` | `.pptx` | python-pptx |

Os arquivos ficam em `backend/outputs/documents/{kind}/` e são servidos pela `:8080` em `GET /api/files/{kind}/{name}`, com `Content-Type` OOXML e `Content-Disposition: attachment`.

> **Escopo:** apenas criação. Edição de arquivos Office existentes está fora do escopo.

## Comandos úteis

```bash
# Backend — gates de qualidade (a partir de backend/)
make arch                 # Regra da Dependência via import-linter (gate obrigatório)
make ruff                 # Linting
make typecheck            # mypy
make test                 # pytest
make check                # suite completa
make help                 # lista os alvos

# Frontend
cd frontend
yarn lint
yarn lint:fix
yarn format
yarn build
```

> `make lint` roda apenas o gate de arquitetura. `ruff` e `mypy` têm dívida pré-existente e ainda não bloqueiam o CI.

## Spec-Driven Development (OpenSddRag)

O projeto usa **OpenSddRag** (servidor MCP `opensddrag`, slug `jeff-ai`) para SDD com memória semântica persistente. Especificações, designs e tarefas vivem no banco, não em arquivos soltos.

```
/opsr:propose → /opsr:spec → /opsr:design → /opsr:tasks → /opsr:apply → /opsr:archive
```

Antes de implementar qualquer feature, busque trabalho existente com `/opsr:search`. Detalhes em [CLAUDE.md](CLAUDE.md).

## Recursos

- [Documentação LangGraph](https://langchain-ai.github.io/langgraph/)
- [DeepAgents](https://github.com/langchain-ai/deepagents)
- [Documentação Ollama](https://ollama.com/)
- [Arquitetura do projeto](docs/ARCHITECTURE.md)
