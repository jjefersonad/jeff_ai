# Arquitetura Jeff AI — Documento de Referência (Baseline as-is)

> **Fonte da verdade:** artefato `arquitetura-jeff-ai-baseline` no OpenSddRag (projeto `jeff-ai`),
> sempre atualizado pelo fluxo SDD. Este arquivo é um **espelho versionado em git** — se ele
> divergir do que foi analisado no código, deve ser atualizado para refletir o baseline.
> Produzido/mantido pela mudança `mapear-arquitetura-projeto`.
>
> **Seções:** 1. Agentes e Grafos LangGraph · 2. Persistência e Backends ·
> 3. Diagrama de Componentes · 4. Integrações e Modelos · 5. Riscos e Dívidas Técnicas.

## 1. Agentes e Grafos LangGraph

O sistema registra **dois grafos** LangGraph em [backend/langgraph.json](../backend/langgraph.json) (chave `graphs`), ambos
construídos com `create_deep_agent` da biblioteca `deepagents`:

```json
"graphs": {
  "agent": "src.agents.requirements_specialist:agent",
  "sdd_agent": "src.agents.sdd.orchestrator:sdd_agent"
}
```

### 1.1 Grafo `agent` — Gerador de Documentos de Requisitos
Arquivo: [backend/src/agents/requirements_specialist.py](../backend/src/agents/requirements_specialist.py)

| Aspecto | Detalhe | Referência |
|---------|---------|------------|
| Papel | Agente **orquestrador**; nunca implementa código diretamente | `requirements_specialist.py:39-72` |
| Modelo | `ollama_model` | `requirements_specialist.py:6,40` |
| Subagentes | `fullstack_subagent` | `requirements_specialist.py:7,41` |
| Ferramentas | `merge_generated_files`, `get_date_time_current` | `requirements_specialist.py:8-9,42` |
| Skills | `/skills/` | `requirements_specialist.py:70` |
| Saída | `backend/outputs/{thread_id}/` (arquivo consolidado obrigatório via `merge_generated_files`) | `requirements_specialist.py:17,24,55` |
| Recursion limit | 1000 | `requirements_specialist.py:74` |

**Fluxo de orquestração** (do system_prompt):
1. Analisa o pedido do usuário.
2. Usa `write_todos` para criar tarefas (cada sessão do documento = uma tarefa).
3. Delega cada tarefa via `task(name="fullstack_subagent", task="...")`.
4. Consolida os resultados e usa **obrigatoriamente** `merge_generated_files` para unificar, na ordem.
5. Salva o arquivo final em `backend/outputs/`.

**Subagente `fullstack_subagent`** ([backend/src/agents/subagents/fullstack.py](../backend/src/agents/subagents/fullstack.py)):
- Escritor técnico que cria seções de documento de requisitos.
- Ferramentas: `ls`, `read_file`, `write_file` (de `src/tools/deep_agent_tools.py`).
- Grava em `backend/outputs/`.

### 1.2 Grafo `sdd_agent` — Pipeline SDD (spec-kit)
Arquivo: [backend/src/agents/sdd/orchestrator.py](../backend/src/agents/sdd/orchestrator.py)

Orquestrador de um **pipeline de 7 fases** que transforma ideias em especificações implementáveis,
cada fase delegada a um subagente via `task()`:

```
1. CONSTITUTION → 2. SPECIFY → 3. CLARIFY → 4. PLAN → 5. ANALYZE → 6. TASKS → 7. IMPLEMENT
```

| Fase | Subagente | Módulo |
|------|-----------|--------|
| 1. Constitution | `constitution_subagent` | `sdd/subagents/constitution.py` |
| 2. Specify | `specify_subagent` | `sdd/subagents/specify.py` |
| 3. Clarify | `clarify_subagent` | `sdd/subagents/clarify.py` |
| 4. Plan | `plan_subagent` | `sdd/subagents/plan.py` |
| 5. Analyze | `analyze_subagent` | `sdd/subagents/analyze.py` |
| 6. Tasks | `tasks_subagent` | `sdd/subagents/tasks.py` |
| 7. Implement | `implement_subagent` | `sdd/subagents/implement.py` |

| Aspecto | Detalhe | Referência |
|---------|---------|------------|
| Modelo | `ollama_model` | `orchestrator.py:6,51` |
| Ferramentas | `create_feature_directory`, `load_template`, `validate_artifact`, `get_sdd_state`, `get_next_feature_number` | `orchestrator.py:16-22,61-67` |
| Templates | `backend/templates/sdd/` | `orchestrator.py:29,43` |
| Saída | `outputs/.specify/` — `memory/constitution.md` (global) + `specs/{NNN}-{feature}/` (spec.md, plan.md, tasks.md, data-model.md, research.md, quickstart.md, validation-report.md, contracts/api-spec.json) | `orchestrator.py:28,84-101` |
| Recursion limit | 1000 | `orchestrator.py:157` |

**Regras-chave:** o orquestrador nunca escreve artefatos diretamente (sempre delega via `task()`);
a constitution é global (uma por projeto); cada subagente de fase é stateless e recebe todo o
contexto no `task()`; há um loop de validação após ANALYZE que re-executa fases em caso de FAIL.

## 2. Persistência e Backends

A persistência tem **duas camadas independentes**: (a) a persistência gerenciada pelo LangGraph API
(checkpointer + store) e (b) o roteamento de sistema de arquivos virtual dos agentes via
`CompositeBackend`.

### 2.1 Checkpointer e Store (Postgres / pgvector)
Configurados **declarativamente** em [backend/langgraph.json](../backend/langgraph.json), ambos apontando para a mesma
instância Postgres via a variável `POSTGRES_URI`:

```json
"checkpointer": { "type": "postgres", "url": "${env:POSTGRES_URI}" },
"store":        { "type": "postgres", "url": "${env:POSTGRES_URI}" }
```

| Camada | Função | Referência |
|--------|--------|------------|
| **Checkpointer** | Histórico de conversas / estado do grafo por `thread_id` | `langgraph.json:7-10` |
| **Store** | Memória de longo prazo (namespace `/memories/`), com busca vetorial pgvector | `langgraph.json:11-14` |

> Os agentes **não** instanciam `PostgresSaver` manualmente — o LangGraph API gerencia a
> persistência automaticamente a partir dessa configuração (comentário em `requirements_specialist.py:37-38`).

### 2.2 CompositeBackend — sistema de arquivos virtual dos agentes
Cada grafo define uma `backend_factory(rt)` que monta um `CompositeBackend` (de
`deepagents.backends`) roteando caminhos para backends distintos. O `thread_id` é obtido de
`rt.config["configurable"]` para isolar a saída por conversa.

**Grafo `agent`** (`requirements_specialist.py:19-34`):

| Rota | Backend | Observação |
|------|---------|------------|
| `default` | `StateBackend(rt)` | Estado efêmero do grafo |
| `{OUTPUTS_DIR}` (`backend/outputs/{thread_id}`) | `FilesystemBackend(root_dir=root, virtual_mode=True)` | Documentos gerados, isolados por thread |
| `/skills/` | `FilesystemBackend(root_dir=SKILLS_DIR)` | Skills carregadas do disco |
| `/memories/` | `StoreBackend(rt)` | Ponte para o Store Postgres/pgvector |

**Grafo `sdd_agent`** (`orchestrator.py:32-47`):

| Rota | Backend | Observação |
|------|---------|------------|
| `default` | `StateBackend(rt)` | Estado efêmero do grafo |
| `{SPECIFY_DIR}` (`outputs/.specify`) | `FilesystemBackend(virtual_mode=True)` | Artefatos SDD por feature |
| `{TEMPLATES_DIR}` (`templates/sdd`) | `FilesystemBackend` | Templates de spec/plan/tasks |
| `/skills/` | `FilesystemBackend(root_dir=SKILLS_DIR)` | Skills |
| `/memories/` | `StoreBackend(rt)` | Store Postgres/pgvector |

> **Nota de dívida técnica:** a função `backend_factory` é praticamente duplicada entre os dois
> orquestradores (ver Seção 5 — Riscos).

### 2.3 Variáveis de ambiente
Carregadas via `load_dotenv()` a partir de `backend/.env`.

| Variável | Obrigatória | Uso |
|----------|-------------|-----|
| `POSTGRES_URI` | ✅ | Checkpointer + Store (`langgraph.json`) |
| `OLLAMA_BASE_URL` | ✅ | Endpoint do servidor Ollama |
| `OLLAMA_MODEL` | ✅ | Nome do modelo Ollama |
| `TAVILY_API_KEY` | ⬜ | Busca web (tool Tavily) |
| `GOOGLE_API_KEY` | ⬜ | Modelo Gemini |
| `LANGSMITH_API_KEY` | ⬜ | Tracing / debug |

## 3. Diagrama de Componentes e Fluxo de Dados

Topologia de deploy conforme [docker-compose.yml](../docker-compose.yml) (rede `jeff_ia-network`). Portas no formato
`host:container`.

```mermaid
flowchart TB
    User([Usuário / Browser])

    subgraph net["Docker network: jeff_ia-network"]
        FE["frontend<br/>Next.js 16 / React 19<br/>:3000→3000<br/>LANGSERVE_URL=localhost:8001"]
        BE["backend<br/>LangGraph API + deepagents<br/>:8001→8000<br/>(Dockerfile.backend)"]

        subgraph graphs["Grafos (langgraph.json)"]
            G1["agent<br/>requirements_specialist<br/>→ fullstack_subagent"]
            G2["sdd_agent<br/>orchestrator<br/>7 fases SDD"]
        end

        PG[("jeff_ia_postgres<br/>pgvector/pgvector:pg15<br/>:5436→5432")]
        RD[("jeff_ia_redis<br/>redis:7-alpine<br/>:6379→6379")]
        PGA["jeff_ia_pgadmin<br/>:5050→80<br/>(profile: admin)"]
    end

    OLL["Ollama<br/>OLLAMA_BASE_URL<br/>(externo/host)"]
    GEM["Gemini<br/>GOOGLE_API_KEY<br/>(externo, opcional)"]
    TAV["Tavily<br/>TAVILY_API_KEY<br/>(externo, opcional)"]

    User -->|HTTP :3000| FE
    FE -->|@langchain/langgraph-sdk<br/>assistants/threads/runs| BE
    BE --> G1
    BE --> G2
    G1 -->|inferência| OLL
    G2 -->|inferência| OLL
    G1 -.->|opcional| GEM
    G1 -.->|busca web| TAV
    BE -->|checkpointer + store<br/>POSTGRES_URI| PG
    BE -->|REDIS_URI| RD
    PGA -->|admin| PG
    G1 -->|FilesystemBackend| FS1[["volume: backend/outputs"]]
    G2 -->|FilesystemBackend| FS2[["outputs/.specify"]]

    classDef ext fill:#f5f5f5,stroke:#999,stroke-dasharray:4 3;
    class OLL,GEM,TAV ext;
```

**Legenda de correspondência (cada nó → artefato real):**

| Nó | Artefato real |
|----|---------------|
| frontend | serviço `frontend` (`docker-compose.yml:36-48`, `frontend/Dockerfile.frontend`) |
| backend | serviço `backend` (`docker-compose.yml:2-34`, `backend/Dockerfile.backend`) |
| agent / sdd_agent | grafos em `backend/langgraph.json:3-6` |
| jeff_ia_postgres | serviço `jeff_ia_postgres` (`docker-compose.yml:50-72`) |
| jeff_ia_redis | serviço `jeff_ia_redis` (`docker-compose.yml:74-82`) |
| jeff_ia_pgadmin | serviço `jeff_ia_pgadmin` (`docker-compose.yml:84-99`, profile `admin`) |
| Ollama / Gemini / Tavily | integrações externas (Seção 4) |
| backend/outputs, outputs/.specify | volumes/saídas dos grafos (Seção 1–2) |

> **Observação:** o serviço `jeff_ia_redis` (`REDIS_URI`) está presente no compose mas não é
> mencionado no `langgraph.json` nem no `CLAUDE.md`; sua função exata (fila/cache do LangGraph API)
> deve ser confirmada — registrado na Seção 5 (Riscos).

## 4. Integrações e Contornos do Sistema

### 4.1 Runtime do backend — dois modos
Existem **dois** runtimes de API no repositório; é importante distinguir qual roda em cada cenário:

| Modo | Como sobe | Grafos expostos | Referência |
|------|-----------|-----------------|------------|
| **Docker (atual)** | Imagem oficial `langchain/langgraph-api:3.11` | `LANGSERVE_GRAPHS` registra **apenas `agent`** | `backend/Dockerfile.backend:1,17` |
| **`langgraph dev`** | CLI LangGraph lendo `langgraph.json` | `agent` **e** `sdd_agent` | `backend/langgraph.json:3-6`, `CLAUDE.md` |
| **`server.py` (alternativo)** | FastAPI custom `uvicorn` :8000 | Carrega grafos de `langgraph.json` dinamicamente | `backend/server.py` |

> O `server.py` é uma **alternativa open-source** compatível com deep-agent-ui, mas **não** é o
> runtime usado pelo `docker-compose.yml` (que usa a imagem oficial). Ver divergências na Seção 5.

**Endpoints expostos** (implementados em `server.py` e compatíveis com a LangGraph API oficial):
`GET /health`, `GET|POST /assistants`, `GET /assistants/{id}`, `GET /assistants/{id}/graph`,
`POST /assistants/search`, `GET|POST /threads`, `GET|DELETE /threads/{id}`,
`GET|POST /threads/{id}/runs`, `GET /threads/{id}/runs/{run_id}`, `GET /graphs`, `GET /graphs/{id}`
(`server.py:190-497`).

O `backend/entrypoint.sh` registra o assistant `agent` (`graph_id="agent"`) via `POST /assistants`
após a API ficar saudável (`entrypoint.sh:17-39`).

### 4.2 Frontend (Next.js) ↔ Backend
- Stack: **Next.js 16 + React 19**, Radix UI + Tailwind (`frontend/`).
- Comunicação via **`@langchain/langgraph-sdk`** apontando para `LANGSERVE_URL` (`http://localhost:8001`
  no compose, `docker-compose.yml:44`).
- Configuração do cliente persistida em `localStorage` sob a chave `deep-agent-config`
  (`deploymentUrl`, `assistantId`, `langsmithApiKey`) — `frontend/src/lib/config.ts`.
- Componentes principais: `ChatInterface`, `ChatMessage`, `ToolCallBox`, `SubAgentIndicator`,
  `TasksFilesSidebar`, `ToolApprovalInterrupt` (`frontend/src/app/components/`).

### 4.3 Provedores de Modelo (LLM)
| Provedor | Classe | Config | Default | Arquivo |
|----------|--------|--------|---------|---------|
| **Ollama** (default) | `ChatOllama` (`langchain_ollama`) | `OLLAMA_MODEL`, `OLLAMA_BASE_URL` | model `deepseek-v4-pro:cloud`, url `http://localhost:11434` | `src/models/ollama_model.py` |
| **Gemini** (alternativo) | `ChatGoogleGenerativeAI` (`langchain_google_genai`) | `GOOGLE_MODEL`, `GOOGLE_API_KEY` | `gemini-2.5-flash` | `src/models/gemini_model.py` |

Ambos usam `temperature=0.0`, `num_ctx=8192`, `timeout=30000`. Os agentes atuais importam
`ollama_model`; o `gemini_model` está definido mas não referenciado pelos grafos ativos.
> O default de `OLLAMA_MODEL` no código (`deepseek-v4-pro:cloud`) diverge do default no
> `docker-compose.yml` (`minimax-m2.7:cloud`) e do `CLAUDE.md` — ver Seção 5.

Para Ollama local, há a variante `docker-compose.ollama.yml`.

### 4.4 MCP OpenSddRag
Servidor MCP `opensddrag` (http://localhost:8000, `.mcp.json`) usado para Spec-Driven Development
com memória semântica persistente. Expõe ferramentas de artefatos SDD (`create_artifact`,
`search_semantic`, `record_trace`, etc.). Skills e comandos em `.claude/skills/opensddrag-*` e
`.claude/commands/opsr/`. Projeto slug: `jeff-ai`. **Este documento é um artefato produzido por esse fluxo.**

## 5. Riscos e Dívidas Técnicas

Itens observados durante o mapeamento. Cada um é acionável como mudança futura própria — **nenhum é
corrigido nesta fase** (o baseline apenas documenta).

| # | Risco / Dívida | Localização | Impacto |
|---|----------------|-------------|---------|
| R1 | **`DATABASE_URL` hardcoded** — não usa `POSTGRES_URI`; host/credenciais fixos (`jeff_ia:jeff_ia@jeff_ia_postgres`) | `backend/server.py:27` | `server.py` só funciona no nome de rede do compose; quebra em outros ambientes; credenciais em texto no código |
| R2 | **`LANGSERVE_GRAPHS` registra apenas `agent`** enquanto `langgraph.json` registra `agent` **e** `sdd_agent` | `backend/Dockerfile.backend:17` vs `backend/langgraph.json:3-6` | No deploy Docker, o `sdd_agent` **não fica exposto**; divergência de fonte de verdade de grafos |
| R3 | **`server.py` custom não é usado pelo compose** (que usa a imagem oficial `langchain/langgraph-api`) | `backend/server.py` vs `backend/Dockerfile.backend:1` | Código alternativo/potencialmente morto; risco de manutenção divergente e confusão sobre qual runtime é canônico |
| R4 | **`backend_factory` duplicado** entre os dois orquestradores (rotas quase idênticas) | `requirements_specialist.py:19-34` e `sdd/orchestrator.py:32-47` | Mudança em roteamento de backend precisa ser feita em dois lugares; risco de deriva |
| R5 | **Serviço `jeff_ia_redis` não documentado** — presente no compose (`REDIS_URI`) mas ausente de `langgraph.json` e `CLAUDE.md` | `docker-compose.yml:13,74-82` | Função incerta (fila/cache?); dependência de runtime não descrita; dificulta operação |
| R6 | **Default de `OLLAMA_MODEL` divergente** entre camadas | `ollama_model.py:10` (`deepseek-v4-pro:cloud`) vs `docker-compose.yml:18` (`minimax-m2.7:cloud`) vs `CLAUDE.md` | Comportamento imprevisível dependendo de onde as envs são resolvidas; confusão sobre o modelo efetivo |
| R7 | **Credenciais Postgres fixas no compose** (`jeff_ia`/`jeff_ia`) e CORS `allow_origins=["*"]` | `docker-compose.yml:53-55`, `langgraph.json:15-17`, `server.py:53-59` | Aceitável em dev; inseguro para qualquer exposição externa |
| R8 | **`gemini_model` definido mas não referenciado** pelos grafos ativos | `src/models/gemini_model.py` | Ou é fallback não-cabeado, ou código morto; intenção precisa ser confirmada |

**Recomendação geral:** priorizar R1–R3 (corretude/deploy) antes de R4–R8 (higiene). Cada item deve
virar uma proposta via `/opsr:propose` quando for endereçado.
