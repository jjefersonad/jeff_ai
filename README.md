# Jeff AI

Jeff AI é um assistente de agente profundo para desenvolvedores que gera documentos de requisitos usando orquestração LangGraph. O sistema utiliza um agente orquestrador principal que delega tarefas para subagentes na criação de documentos de requisitos estruturados.

## Funcionalidades

- Geração automática de documentos de especificação de requisitos
- Orquestração inteligente de tarefas via LangGraph
- Persistência de estado com PostgreSQL
- Interface web moderna para interação com o agente
- Suporte a múltiplos modelos LLM (Ollama, Gemini)

## Tech Stack

**Backend**
- Python 3.11+
- LangGraph para orquestração
- DeepAgents para implementação de agentes
- PostgreSQL com pgvector para persistência

**Frontend**
- Next.js 16
- React 19
- Tailwind CSS
- Radix UI

## Quickstart

### Prerequisites

- Docker Compose
- Servidor Ollama em execução
- **LANGSMITH_API_KEY** (obrigatório para LangGraph API)

### Configuração Obrigatória

#### 1. Obter LangSmith API Key

1. Acesse [https://smith.langchain.com](https://smith.langchain.com)
2. Faça login ou crie uma conta
3. Vá em **Settings** → **API Keys**
4. Clique em **Create API Key**
5. Copie a chave gerada

#### 2. Configurar Variáveis de Ambiente

Edite o arquivo `backend/.env`:

```bash
# LangSmith API Key (obrigatório para LangGraph API)
LANGSMITH_API_KEY=sua_chave_aqui

# Ollama - IP do servidor Ollama
OLLAMA_BASE_URL=http://10.0.0.214:11434

# Modelo Ollama (recomendado: minimax-m2.7:cloud)
OLLAMA_MODEL=minimax-m2.7:cloud
```

**Nota**: Se o Ollama estiver rodando localmente, use `http://host.docker.internal:11434` ou `http://localhost:11434`.

### Configuração do Banco de Dados

```bash
docker compose up -d
```

### Backend

```bash
cd backend

# Install dependencies
pip install -e ".[dev]"

# Start LangGraph API server
langgraph dev

# Chat interactivo (em outro terminal)
python main.py
```

### Frontend

```bash
cd frontend

# Install dependencies
yarn install

# Development server
yarn dev
```

Acesse a aplicação em [http://localhost:3000](http://localhost:3000).

### Docker (Alternativo)

Todas as aplicações podem ser executadas via Docker Compose:

```bash
docker-compose up -d
```

**Portas expostas:**
- Frontend: `http://localhost:3000`
- Backend: `http://localhost:8000`
- pgAdmin: `http://localhost:5050` (execute `docker-compose --profile admin up`)

**Variáveis necessárias no `backend/.env`:**
- `LANGSMITH_API_KEY` - Chave do LangSmith (obrigatório)
- `OLLAMA_BASE_URL` - URL do servidor Ollama
- `OLLAMA_MODEL` - Modelo a ser usado (`minimax-m2.7:cloud`)

## Configuração

### Variáveis de Ambiente (Backend)

Configure as variáveis no arquivo `backend/.env`:

| Variável | Descrição | Exemplo |
|----------|-----------|---------|
| `LANGSMITH_API_KEY` | **Obrigatório** - Chave do LangSmith | `lsv2_pt_...` |
| `OLLAMA_BASE_URL` | Endpoint do servidor Ollama | `http://localhost:11434` |
| `OLLAMA_MODEL` | Modelo Ollama a ser usado | `minimax-m2.7:cloud` |
| `POSTGRES_URI` | String de conexão PostgreSQL (automático) | `postgresql://jeff_ia:jeff_ia@jeff_ia_postgres:5432/jeff_ia` |

### Interface Web

Ao acessar a interface (http://localhost:3000), configure:

- **Deployment URL**: `http://localhost:8000`
- **Assistant ID**: O ID do assistant criado automaticamente (ex: `fe096781-5601-53d2-b2f6-0d3403f7e9ca`)

## Arquitetura

```
┌─────────────────────────────────────────────────────────────┐
│                        Frontend (Next.js)                    │
│                    http://localhost:3000                     │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                     LangGraph API Server                     │
│                      langgraph dev                          │
│                    http://127.0.0.1:2024                     │
└─────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
┌─────────────────────────┐   ┌─────────────────────────┐
│   Requirements Specialist│   │      PostgreSQL         │
│    (Agente Orquestrador) │   │  (Checkpoint/Store)     │
└─────────────────────────┘   └─────────────────────────┘
              │
              ▼
┌─────────────────────────┐
│    Fullstack Subagent   │
│  (Geração de Seções)    │
└─────────────────────────┘
              │
              ▼
┌─────────────────────────┐
│       Tools             │
│ - Tavily Search         │
│ - File Operations       │
│ - Merge Files           │
└─────────────────────────┘
```

### Estrutura de Diretórios

```
jeff_ai/
├── backend/
│   ├── src/
│   │   ├── agents/           # Agentes e orquestração
│   │   │   ├── requirements_specialist.py
│   │   │   └── subagents/
│   │   │       └── fullstack.py
│   │   ├── models/           # Configurações de modelos LLM
│   │   │   ├── ollama_model.py
│   │   │   └── gemini_model.py
│   │   └── tools/            # Ferramentas personalizadas
│   │       ├── tavily_tool.py
│   │       ├── technical_spec_tools.py
│   │       └── zip_files_tool.py
│   ├── skills/               # Skills do DeepAgent
│   └── outputs/              # Documentos gerados
├── frontend/
│   ├── src/                  # Componentes e páginas Next.js
│   └── public/
└── docker-compose.yml        # PostgreSQL + pgAdmin
```

## Uso

1. Inicie o servidor LangGraph: `cd backend && langgraph dev`
2. Inicie o frontend: `cd frontend && yarn dev`
3. Acesse [http://localhost:3000](http://localhost:3000)
4. Configure a URL (`http://127.0.0.1:2024`) e o Assistant ID (`agent`)
5. Envie uma solicitação para gerar documentação de requisitos

## Documentação Gerada

Os documentos de requisitos são salvos em `backend/outputs/` no formato Markdown, contendo:

- Visão geral do sistema
- Requisitos funcionais
- Requisitos não funcionais
- Casos de uso
- Modelagem de dados
- Interface de usuário
- Considerações de segurança

## Comandos Úteis

```bash
# Backend
cd backend
ruff check .              # Linting
mypy .                    # Type checking
pytest                    # Executar testes

# Frontend
cd frontend
yarn lint                 # Verificar problemas
yarn lint:fix             # Corrigir automaticamente
yarn format               # Formatar código
```

## Recursos

- [Documentação LangGraph](https://langchain-ai.github.io/langgraph/)
- [DeepAgents](https://github.com/langchain-ai/deepagents)
- [Documentação Ollama](https://ollama.com/)